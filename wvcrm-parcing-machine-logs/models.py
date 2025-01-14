from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Float, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()

class status_machine_logs(Base):
    __tablename__ = 'status_machine_logs'
    
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer)
    type_machine = Column(String(255))
    machine_id = Column(Integer, ForeignKey('laser_park.id'))
    user_id = Column(Integer, ForeignKey('user.id'))
    date_start = Column(DateTime(timezone=True), nullable=True)
    date_end = Column(DateTime(timezone=True), nullable=True)
    processing_time = Column(Integer, nullable=True)
    move_time = Column(Integer, nullable=True)
    delay_time = Column(Integer, nullable=True)
    total_time_start = Column(Integer, nullable=True)
    total_time_end = Column(Integer, nullable=True)
    pause_time = Column(Integer, nullable=True)
    status = Column(String(255))
    source_file = Column(String(255))
    source_line = Column(Integer)
    user = relationship("user")
    laser_park = relationship("laser_park")

    def __init__(self, _task_id, _type_machine, _machine_id, _user_id, _date_start, _date_end, _processing_time, _move_time, _delay_time, _total_time_start, _total_time_end, _pause_time, _status, _source_file, _source_line):
        self.task_id = _task_id
        self.type_machine = _type_machine
        self.machine_id = _machine_id
        self.user_id = _user_id
        self.date_start = _date_start
        self.date_end = _date_end
        self.processing_time = _processing_time
        self.move_time = _move_time
        self.delay_time = _delay_time
        self.total_time_start = _total_time_start
        self.total_time_end = _total_time_end
        self.pause_time = _pause_time
        self.status = _status
        self.source_file = _source_file
        self.source_line = _source_line


class settings_main(Base):
    __tablename__ = 'settings_main'
    id = Column(Integer, primary_key=True)

    name = Column(String(255))
    value = Column(String(255))

    def __init__(self, _name, _value):
        self.name = _name
        self.value = _value


class user(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    id_rezhemvse = Column(Integer)

    FIO = Column(String(100))
    type_production_id = Column(Integer, ForeignKey("type_production.id"))
    type_cpec_id = Column(Integer)
    description = Column(String(100))
    login = Column(String(100))
    password = Column(String(100))
    telegram_id = Column(String(100))

    OrderAccessLevel = Column(Integer)

    isWebAdmin = Column(Boolean)
    isMaster = Column(Boolean)
    isControl = Column(Boolean)
    isStorage = Column(Boolean)
    isAdmin = Column(Boolean)
    isDesignEngineer = Column(Boolean)
    isNotIssued = Column(Boolean)
    isActive = Column(Boolean)
    isSA = Column(Boolean)
    isDebug = Column(Boolean)

    avatar_url = Column(String(1024))
    label = Column(String(255))
    p_rez = Column(String(255))

    isLeave = Column(Boolean)


class task_complete(Base):
    __tablename__ = 'task_complete'
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("task.id"))
    user_id = Column(Integer, ForeignKey("user.id"))
    count = Column(Float)
    date_start = Column(DateTime(timezone=True))
    date_end = Column(DateTime(timezone=True))
    old_date_start = Column(DateTime(timezone=True))
    old_date_end = Column(DateTime(timezone=True))
    isRework = Column(Boolean)
    isDone = Column(Boolean)
    isIssuedMaterial = Column(Boolean)
    description = Column(String(100))
    user = relationship('user', backref='task_complete', uselist=False, lazy=True)

    def __init__(self, _task_id, _user_id, _count, _date_start, _date_end, _description):
        self.task_id = _task_id
        self.user_id = _user_id
        self.count = _count
        self.date_start = _date_start
        self.date_end = _date_end
        self.description = _description 

class task_complete_bend(Base):
    __tablename__ = 'task_complete_bend'
    id = Column(Integer, primary_key=True)
    prod_id = Column(Integer)
    bend_park_id = Column(Integer, ForeignKey("bend_park.id"))
    user_id = Column(Integer, ForeignKey("user.id"))
    count = Column(Integer)
    date_s = Column(DateTime(timezone=True))
    date_e = Column(DateTime(timezone=True))
    description = Column(String(1024))

    us = relationship('user', backref='task_complete_bend', uselist=False, lazy=True)
    bend_park = relationship('bend_park', backref='task_complete_bend', uselist=False, lazy=True)


class bend_park(Base):
    __tablename__ = 'bend_park'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(String(255))
    state = Column(String(255))


class task(Base):
    __tablename__ = 'task'
    id = Column(Integer, primary_key=True)
    operation_number = Column(Integer)
    type_cpec_id = Column(Integer)
    production_id = Column(Integer, ForeignKey("production.id"))
    date_create = Column(DateTime(timezone=True))
    date_deadline = Column(DateTime(timezone=True))
    description = Column(String(100))
    count_rework = Column(Integer)
    count_reject = Column(Integer)
    team_number = Column(Integer)
    pos_day = Column(Integer)
    task_complete = relationship('task_complete', backref='task', lazy=False)

    def __init__(self, _operation_number, _production_id, _date_create, _date_deadline, _description):
        self.operation_number = _operation_number
        self.production_id = _production_id
        self.date_create = _date_create
        self.date_deadline = _date_deadline
        self.description = _description


class laser_production(Base):
    __tablename__ = 'laser_production'
    id = Column(Integer, primary_key=True)
    production_id = Column(Integer, ForeignKey("production.id"))
    thickness = Column(Float)
    width = Column(Float)
    length = Column(Float)
    laser_method_id = Column(Integer) #, ForeignKey("Laser_method.id"))
    laser_machine_id = Column(Integer, ForeignKey("laser_machine.id"))
    laser_power_id = Column(Integer, ForeignKey("laser_power.id"))
    laser_material_id = Column(Integer) #, ForeignKey("Laser_material.id"))
    isOwner = Column(Boolean)
    laser_name = relationship('laser_machine', backref='laser_production', lazy=True)
    laser_power = relationship('laser_power', backref='laser_production', lazy=True)


class laser_power(Base):
    __tablename__ = 'laser_power'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))


class laser_machine(Base):
    __tablename__ = 'laser_machine'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    active = Column(Boolean)


class laser_park(Base):
    __tablename__ = 'laser_park'
    id = Column(Integer, primary_key=True)
    laser_id = Column(Integer, ForeignKey('laser_machine.id'))
    power_id = Column(Integer, ForeignKey('laser_power.id'))
    stor_id = Column(Integer)

    laser_machine = relationship("laser_machine")
    laser_power = relationship("laser_power")


class production(Base):
    __tablename__ = 'production'
    id = Column(Integer, primary_key=True)
    contract = Column(String(100))
    machine_id = Column
    type_production_id = Column(Integer)