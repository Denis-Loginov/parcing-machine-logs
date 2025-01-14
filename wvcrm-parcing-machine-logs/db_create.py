from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def create_db1(db_config, is_engine=False):
    db_uri = f"{db_config['DB_TYPE']}://{db_config['DB_USER']}:{db_config['DB_PASSWORD']}@{db_config['DB_HOST']}/{db_config['DB_NAME']}?charset=cp1251"
    engine = create_engine(db_uri, pool_size=30, max_overflow=0)

    if is_engine:
        return engine

    Session = sessionmaker(bind=engine)
    session = Session()
    return session

db_config = {
    "DB_USER": "db_server_002",
    "DB_PASSWORD": "fr456ttr44",
    "DB_HOST": "192.168.135.192",
    "DB_NAME": "woodver",
    "DB_TYPE": "mysql",
    "URI_NAME": "SQLALCHEMY_DATABASE_URI"
}
