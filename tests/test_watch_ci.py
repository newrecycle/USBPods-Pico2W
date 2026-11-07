"""CI watcher identity, aggregate completion and timeout contracts; no network/model calls."""
import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
import types
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('watch_ci',Path(__file__).resolve().parents[1]/'tools/watch_ci.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
SHA='a'*40

def run(name='firmware',id=1,status='completed',conclusion='success',sha=SHA,event='push',attempt=1):
    return dict(workflowName=name,databaseId=id,status=status,conclusion=conclusion,headSha=sha,event=event,attempt=attempt)

class Tests(unittest.TestCase):
    def test_idle_guard_checks_identity_unfinished_and_overlapping_turns(self):
        session='12345678-1234-1234-1234-123456789abc'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'session.jsonl'
            rows=[dict(type='session_meta',payload=dict(id=session))]
            def write():path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            def event(kind,turn):rows.append(dict(type='event_msg',payload=dict(type=kind,turn_id=turn)));write()
            write();self.assertFalse(w.session_is_idle(path,session))
            event('task_started','a');self.assertFalse(w.session_is_idle(path,session))
            event('task_started','b');event('task_complete','b')
            self.assertFalse(w.session_is_idle(path,session))
            event('turn_aborted','a');self.assertTrue(w.session_is_idle(path,session))
            with self.assertRaises(RuntimeError):w.session_is_idle(path,'wrong')
            with path.open('a',encoding='utf-8') as out:out.write('{"type":')
            self.assertFalse(w.session_is_idle(path,session))
            path.write_text(json.dumps(dict(type='session_meta',payload=dict(id=session)))+'\n'+
                            json.dumps(dict(type='event_msg',payload=dict(type='task_complete',turn_id='orphan')))+'\n')
            self.assertFalse(w.session_is_idle(path,session))
            path.write_text('')
            self.assertFalse(w.session_is_idle(path,session))

    def test_identity_and_newest_run(self):
        rows=[run(id=1),run(id=2,status='in_progress'),run(id=3,sha='b'*40),run(id=4,event='pull_request')]
        self.assertEqual(w.select_runs(rows,SHA,['firmware'])['firmware']['databaseId'],2)
        same_id=[run(id=7,attempt=2,status='in_progress',conclusion=None),
                 run(id=7,attempt=1,status='completed',conclusion='success')]
        selected=w.select_runs(same_id,SHA,['firmware'])['firmware']
        self.assertEqual(selected['attempt'],2)
        self.assertFalse(w.wait_for_ci('repo',SHA,['firmware'],60,1,
                         fetch=lambda:same_id)['success'])

    def test_waits_for_all_workflows_and_retains_failure(self):
        states=iter([[run(),run('host',status='in_progress')],
                     [run(),run('host',conclusion='failure')]])
        with patch.object(w.time,'sleep'):
            r=w.wait_for_ci('repo',SHA,['firmware','host'],60,100,fetch=lambda:next(states))
        self.assertEqual(r['state'],'completed');self.assertFalse(r['success'])
        self.assertEqual(len(r['runs']),2)

    def test_success_requires_all_success(self):
        r=w.wait_for_ci('repo',SHA,['firmware'],60,100,fetch=lambda:[run()])
        self.assertTrue(r['success'])
        for conclusion in ['cancelled','skipped','timed_out','neutral']:
            r=w.wait_for_ci('repo',SHA,['firmware'],60,100,fetch=lambda:[run(conclusion=conclusion)])
            self.assertFalse(r['success'])

    def test_missing_workflow_times_out(self):
        with patch.object(w.time,'monotonic',side_effect=[0,0,2,2]),patch.object(w.time,'sleep'):
            r=w.wait_for_ci('repo',SHA,['firmware','host'],60,1,fetch=lambda:[run()])
        self.assertEqual(r['state'],'timeout');self.assertEqual(r['missing'],['host']);self.assertFalse(r['success'])

    def test_callback_resumes_exact_session_after_record_written(self):
        session='12345678-1234-1234-1234-123456789abc'
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'new'
            session_log=Path(tmp)/'session.jsonl';session_log.touch()
            args=['watch_ci','--sha',SHA,'--output',str(output),'--resume-session',session,'--session-owner','cli','--session-log',str(session_log)]
            def invoke(argv,**kwargs):
                self.assertTrue((output/'completion.json').exists())
                self.assertEqual(argv[:4],['codex','exec','resume',session])
                self.assertNotIn('--last',argv)
                self.assertFalse(any('bypass' in x for x in argv))
                return types.SimpleNamespace(returncode=0)
            with patch('sys.argv',args),patch.object(w.shutil,'which',side_effect=lambda x:x),patch.object(w,'wait_for_ci',return_value=dict(state='completed',success=False,runs=[],missing=[])),patch.object(w,'wait_for_idle',return_value=True),patch.object(w.subprocess,'run',side_effect=invoke):
                self.assertEqual(w.main(),1)
            self.assertFalse(json.loads((output/'completion.json').read_text())['success'])
            result=json.loads((output/'callback-status.json').read_text())
            self.assertEqual(result['returncode'],0)
            self.assertEqual(result['state'],'cli_process_exited_unverified')
            self.assertFalse(result['desktop_turn_observed'])

    def test_desktop_owned_session_is_record_only_even_with_idle_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'session.jsonl';log.touch()
            args=['watch_ci','--sha',SHA,'--output',str(Path(tmp)/'new'),
                  '--resume-session','12345678-1234-1234-1234-123456789abc',
                  '--session-log',str(log)]
            with patch('sys.argv',args),patch.object(w.shutil,'which',side_effect=lambda x:x),patch.object(w.subprocess,'run') as resume:
                with self.assertRaises(SystemExit) as err:w.main()
                self.assertEqual(err.exception.code,2)
                resume.assert_not_called()
            self.assertFalse((Path(tmp)/'new').exists())

    def test_busy_session_never_resumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'new';log=Path(tmp)/'session.jsonl';log.touch()
            args=['watch_ci','--sha',SHA,'--output',str(output),'--resume-session','12345678-1234-1234-1234-123456789abc','--session-owner','cli','--session-log',str(log)]
            with patch('sys.argv',args),patch.object(w.shutil,'which',side_effect=lambda x:x),patch.object(w,'wait_for_ci',return_value=dict(state='completed',success=True,runs=[],missing=[])),patch.object(w,'wait_for_idle',return_value=False),patch.object(w.subprocess,'run') as resume:
                self.assertEqual(w.main(),2);resume.assert_not_called()
            self.assertEqual(json.loads((output/'callback-status.json').read_text())['state'],'session_busy')

if __name__=='__main__':unittest.main()
