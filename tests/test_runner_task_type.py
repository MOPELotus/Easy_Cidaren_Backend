import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock
from api.runner import HeadlessTaskRunner
from publicInfo.publicInfo import PublicInfo

class RunnerTaskTypeTests(unittest.TestCase):
    def test_class_study_and_test_use_class_api_namespace(self):
        for kind in (1,2):
            runner=object.__new__(HeadlessTaskRunner)
            runner.public=SimpleNamespace(course_id='',all_unit={'task_list':[{'task_name':'task','list_id':'unit','task_id':7}]},all_unit_name=[],word_list=[])
            runner._complete_practice=Mock();runner._answer_current_task=Mock();runner._result=Mock(return_value={})
            def check_namespace(public):
                self.assertEqual(PublicInfo.task_type,'ClassTask');self.assertEqual(PublicInfo.task_type_int,2)
            with patch('api.runner.get_all_unit',side_effect=check_namespace),patch('api.runner.get_unit_words'),patch('api.runner.handle_word_result'):
                runner.run_class_task({'task_name':'task','task_type':kind,'task_id':7,'course_id':'book'})
