"""Headless task runner extracted from the upstream Qt ``TaskWorker``.

The request order intentionally mirrors Easy_Cidaren's working desktop flow.
This module only replaces Qt signals with callbacks so callers can embed the
donor without importing its user interface.
"""

from __future__ import annotations

import pathlib
import random
import time
from collections.abc import Callable, Mapping

from answer_questions.answer_questions import answer, jump_read, submit
from api.lotus_tiku import load_settings
from api.basic_api import get_all_unit, get_book_all_words, get_unit_words
from api.main_api import get_exam, get_task_score, select_all_word, skip_exam
from decryptencrypt.debase64 import debase64
from publicInfo.publicInfo import PublicInfo
from util.basic_util import extract_book_word, query_word_unit
from util.handle_word_list import handle_word_result


ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]


class HeadlessTaskRunner:
    """Run one Provider-native task with the donor's original state machine."""

    def __init__(
        self,
        root: str | pathlib.Path,
        *,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
    ) -> None:
        self.public = PublicInfo(str(pathlib.Path(root)))
        self._progress = progress or (lambda _done, _total, _message: None)
        self._log = log or (lambda _message: None)

    def set_answer_override(self, callback):
        raise ValueError("当前版本只使用荷花题库，不接受外部答案覆盖。")

    def _emit_progress(self, message: str = "正在执行词达人原生答题流程") -> None:
        exam = self.public.exam
        if not isinstance(exam, Mapping):
            return
        done = int(exam.get("topic_done_num") or 0)
        total = int(exam.get("topic_total") or 0)
        self._progress(done, total, message)

    def _answer_current_task(self) -> None:
        public = self.public
        if not public.word_list:
            try:
                get_unit_words(public)
                handle_word_result(public)
            except Exception as error:
                self._log(f"加载词表失败，继续由荷花题库解答：{error}")
        get_exam(public)
        if public.exam == "complete":
            self._log("上游报告任务已经完成")
            return
        public.topic_code = public.exam["topic_code"]
        self._emit_progress()
        while public.exam != "complete":
            mode = public.exam["topic_mode"]
            if mode == 0:
                jump_read(public)
            else:
                option = answer(public, mode)
                if option is None:
                    public.topic_code = public.exam["topic_code"]
                    public.skip_count += 1
                    skip_exam(public)
                else:
                    submit(public, option)
            self._emit_progress()
            if public.exam != "complete":
                time.sleep(random.randint(public.min_time, public.max_time))

    def _complete_practice(self, unit: str, progress: int, task_id=None) -> None:
        public = self.public
        public.now_unit = unit
        public.task_id = task_id
        get_unit_words(public)
        handle_word_result(public)
        exist_little_task = None
        raw = public.get_word_list_result
        if isinstance(raw, Mapping) and "data" in raw:
            data = raw["data"]
            if isinstance(data, Mapping):
                exist_little_task = data.get("exist_little_task")
            elif "jv" in raw:
                decoded = debase64(data, raw.get("jv"))
                if isinstance(decoded, Mapping):
                    exist_little_task = decoded.get("exist_little_task")
                    public.get_word_list_result = decoded
        if (progress < 2 and exist_little_task != 1) or exist_little_task == 2:
            try:
                select_all_word({f"{public.course_id}:{unit}": public.word_list}, public.task_id)
            except Exception:
                self._log("上游选择单词接口报告任务已经开启，继续答题")
        self._answer_current_task()

    def run_unit(self, unit: Mapping) -> dict:
        load_settings(self.public.path)
        public = self.public
        public.course_id = unit.get("course_id") or public.course_id
        public.now_unit = unit.get("list_id") or unit.get("id")
        public.task_id = unit.get("task_id")
        PublicInfo.task_type_int = 1
        PublicInfo.task_type = "StudyTask"
        self._log(f"开始自学章节：{unit.get('task_name') or unit.get('list_name') or public.now_unit}")
        self._complete_practice(public.now_unit, int(unit.get("progress") or 0), public.task_id)
        return self._result()

    def run_class_task(self, task: Mapping) -> dict:
        load_settings(self.public.path)
        public = self.public
        task_name = str(task.get("task_name") or task.get("name") or task.get("task_id") or "词达人任务")
        public.course_id = task.get("course_id") or public.course_id
        public.release_id = task.get("release_id") or ""
        task_type = int(task.get("task_type") or 1)
        PublicInfo.task_type_int = task_type
        PublicInfo.task_type = "ClassTask" if task_type == 2 else "StudyTask"

        get_all_unit(public)
        units = public.all_unit.get("task_list", []) if isinstance(public.all_unit, Mapping) else []
        matched = None
        for unit in units:
            if not isinstance(unit, Mapping):
                continue
            public.all_unit_name.append(unit.get("list_id"))
            if unit.get("task_name") == task_name:
                matched = unit
                break

        progress = int(task.get("progress") or 0)
        if matched is None:
            public.is_self_built = True
            public.task_id = task.get("task_id") or task.get("id")
            if task_type == 1:
                get_unit_words(public)
                query_word_unit(public)
                raw = public.get_word_list_result
                little = raw.get("exist_little_task") if isinstance(raw, Mapping) else None
                if (progress < 2 and little != 1) or little == 2:
                    select_all_word(public.word_list, public.task_id)
            get_book_all_words(public)
            extract_book_word(public)
            self._answer_current_task()
        elif task_type == 1:
            self._complete_practice(
                matched.get("list_id"),
                progress,
                task.get("task_id") or matched.get("task_id"),
            )
        else:
            public.now_unit = matched.get("list_id")
            public.task_id = task.get("task_id") or matched.get("task_id")
            get_unit_words(public)
            handle_word_result(public)
            self._answer_current_task()
        return self._result()

    def _result(self) -> dict:
        score = get_task_score(self.public)
        return {
            "complete": self.public.exam == "complete",
            "score": score,
            "right_count": self.public.right_count,
            "wrong_count": self.public.wrong_count,
            "skip_count": self.public.skip_count,
        }

