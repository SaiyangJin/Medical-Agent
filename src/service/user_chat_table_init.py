import datetime

from sqlalchemy import (Table, MetaData, Column, Text, JSON, Boolean, DateTime,
                        TIMESTAMP, BigInteger, DOUBLE,Float)
from sqlalchemy.dialects.postgresql import JSONB

from src.parent_child_chunk.init_model import engine
meta_data = MetaData()
user_chat_request_table = Table("user_chat_request", meta_data,
                                Column("id", BigInteger, primary_key=True),
                                Column("question", Text, nullable=False),
                                Column("answer", Text, nullable=False),
                                Column("trace_id", Text, nullable=False),
                                Column("cost_time", Float, nullable=False),
                                Column("is_system_error", Boolean, nullable=False),
                                Column("create_time", DateTime, nullable=False, default=datetime.datetime.now))
if __name__ == '__main__':

    #创建表
    meta_data.drop_all(engine)
    meta_data.create_all(engine)