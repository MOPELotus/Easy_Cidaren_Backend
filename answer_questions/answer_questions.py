"""Task submission helpers; Lotus is the only answer provider."""
import random
import time

from api.main_api import submit_result, next_exam
from api.lotus_tiku import answer_from_lotus
from log.log import Log
from publicInfo.publicInfo import PublicInfo

query_answer = Log('answer_questions')

# submit
def submit(public_info: PublicInfo, option: int or str or dict):
    """
    提交答案
    :param public_info:
    :param option: 选项索引或单词
    :return: None
    """
    public_info.topic_code = public_info.exam['topic_code']
    # submit result
    if type(option) == dict:
        # resolve mode == 31
        for answer_index in option.values():
            submit_result(public_info, answer_index)
    else:
        submit_result(public_info, option)
    #
    time.sleep(random.randint(1, 2))
    # get next exam
    next_exam(public_info)


# skip read word
def jump_read(public_info):
    """
    跳过阅读卡片
    """
    time.sleep(random.randint(1, 3))
    query_answer.logger.info("跳过阅读单词卡片")
    next_exam(public_info)
    public_info.topic_code = public_info.exam['topic_code']


def answer(public_info, mode):
    return answer_from_lotus(public_info, mode)
