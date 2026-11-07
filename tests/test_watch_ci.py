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

def run(name='firmware',id=1,status='completed',conclusion='success',sha=SHA,event='push'):
    return dict(workflowName=name,databaseId=id,status=status,conclusion=conclusion,headSha=sha,event=event)

class Tests(unittest.TestCase):
    def test_identity_and_newest_run(self):
        rows=[run(id=1),run(id=2,status='in_progress'),run(id=3,sha='b'*40),run(id=4,event='pull_request')]
        self.assertEqual(w.select_runs(rows,SHA,['firmware'])['firmware']['databaseId'],2)

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
            args=['watch_ci','--sha',SHA,'--output',str(output),'--resume-session',session]
            def invoke(argv,**kwargs):
                self.assertTrue((output/'completion.json').exists())
                self.assertEqual(argv[:4],['codex','exec','resume',session])
                self.assertNotIn('--last',argv)
                self.assertFalse(any('bypass' in x for x in argv))
                return types.SimpleNamespace(returncode=0)
            with patch('sys.argv',args),patch.object(w.shutil,'which',side_effect=lambda x:x),patch.object(w,'wait_for_ci',return_value=dict(state='completed',success=False,runs=[],missing=[])),patch.object(w.subprocess,'run',side_effect=invoke):
                self.assertEqual(w.main(),1)
            self.assertFalse(json.loads((output/'completion.json').read_text())['success'])
            self.assertEqual(json.loads((output/'callback-status.json').read_text())['returncode'],0)

if __name__=='__main__':unittest.main()
