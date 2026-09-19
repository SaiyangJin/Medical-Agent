from src import find
from src import dirty_data_clean

def test_find():
    find("裸體恐懼症", 5)


def test_clean_dirty_data():
    dirty_data_clean()


if __name__ == '__main__':
    test_clean_dirty_data()