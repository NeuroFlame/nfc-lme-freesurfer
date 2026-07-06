import os

import simplejson as json


class CacheSerialStore():
    """
    CacheSerialStore handles all cache parameters and storage used by the executors.
    This class remains the same across computations.
    """
    def __init__(self, base_dir):
        """
        Initializes the cache directories and the temporary cache data file paths
        """
        self._cache_dir = os.path.join(base_dir, "_temp_cache")
        self._cache_file_path = os.path.join(self._cache_dir, "client_cache_serial_store.json")
        os.makedirs(self._cache_dir, exist_ok=True)  # succeeds even if directory exists.

        self.client_cache_dict = {}
        if os.path.exists(self._cache_file_path):
            with open(self._cache_file_path, "r") as f:
                self.client_cache_dict = json.load(f)

        self.client_cache_dir = os.path.join(self._cache_dir, "client_computation_cache")
        os.makedirs(self.client_cache_dir, exist_ok=True)  # succeeds even if directory exists.

    def get_cache_dict(self):
        """
        Returns cache data dictionary
        """
        return self.client_cache_dict

    def get_cache_dir(self):
        """
        Returns cache data storage directory
        """
        return self.client_cache_dir

    def update_cache_dict(self, cache_dict):
        """
        Updates cache data dictionary
        """
        self.client_cache_dict.update(cache_dict)
        with open(self._cache_file_path, "w") as f:
            json.dump(self.client_cache_dict, f)

    def remove_cache(self):
        """
        Removes the local cache data dictionary file and also cache data directory
        """
        import shutil
        shutil.rmtree(self._cache_dir, ignore_errors=True)
