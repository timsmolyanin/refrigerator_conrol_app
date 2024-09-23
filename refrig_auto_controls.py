from collections.abc import Callable, Iterable, Mapping
from threading import Thread
from typing import Any
from time import sleep
from copy import deepcopy

class refrigAutoControls(Thread):
    def __init__(self, values_dict, error_queue, cmd_func, update_period = .5, name: str | None = None) -> None:
        try:
            super().__init__(name=name, daemon=True)
            self.values_dict = values_dict
            self.err_queue = error_queue
            self.send_command = cmd_func
            self.update_period = update_period
        except Exception as err:
            raise type(err)(f'refrigAutoControls init: {err}')


    def run(self):
        try:
            while True:
                sleep(self.update_period)
                cur_values = deepcopy(self.values_dict) # get a local copy of shared values dict to avoid blocking
        except Exception as err:
            self.err_queue.put(f'refrigAutoControls: {err}')


    def process(self, cur_values):
        return