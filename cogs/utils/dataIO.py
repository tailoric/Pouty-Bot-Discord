import logging
from os import path
import json
class DataIO():
    def __init__(self):
        self.logger = logging.getLogger("PoutyBot")
        self.data_path = "data/"

    def save_json(self, filename, data):
        """save file as json file at file path"""
        file_path = self.data_path+filename+".json"
        with open(self.data_path+filename+".json", encoding="utf-8", mode="w") as file:
            json.dump(data, file)
            self.logger.info("save info to {}".format(file_path))
        return data

    def load_json(self, filename, as_list=False):
        """load file as json file"""
        file_path = self.data_path+filename+".json"
        if not path.exists(file_path):
            data = [] if as_list else {}
            self.save_json(filename, data)
            self.logger.warning("json file {} not found, creating empty file".format(file_path))
        with open(file_path, mode="r") as json_file:
            return json.load(json_file)
