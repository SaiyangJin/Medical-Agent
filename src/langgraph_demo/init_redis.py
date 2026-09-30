import redis
redis_template=redis.Redis(host="127.0.0.1",port=6379,db=0,password="123456",protocol=2,decode_responses=True)
#这个protocol是因为redis-py和redis版本不匹配，造成的降低
#要加入decoer参数，不然存入会异常

# if __name__ == '__main__':
    # redis_template.json("utf-8","utf-8").set("test","{'114514':'1919810'}")
