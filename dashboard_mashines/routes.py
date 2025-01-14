import calendar

from flask import jsonify, render_template, request, render_template
from flask_login import login_required
from sqlalchemy import func, text, and_

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta

from webPlanner import app
from webPlanner.db_create import create_db1
from webPlanner.models import *


def get_weekly_downtime(selected_date):

    # Определяем начало и конец месяца
    year = selected_date.year
    month = selected_date.month
    date_start = selected_date.replace(day=1)
    last_day_of_month = monthrange(year, month)[1]
    date_end = selected_date.replace(day=last_day_of_month)

    _ses = create_db1()
    try:
        results = _ses.query(
            Downtime_machines.machine_id,
            Downtime_machines.type_machine,
            Downtime_machines.type_id,
            func.sum(func.timestampdiff(text('SECOND'), Downtime_machines.date_start, Downtime_machines.date_end)).label('total_downtime'),
            Downtime_machines.date_start
        ).outerjoin(
            laser_park, laser_park.id == Downtime_machines.machine_id
        ).filter(
            Downtime_machines.date_start >= date_start,
            Downtime_machines.date_start <= date_end,
            Downtime_machines.type_machine.in_(["Laser"])
        ).group_by(
            Downtime_machines.machine_id,
            Downtime_machines.type_machine,
            Downtime_machines.type_id,
            Downtime_machines.date_start
        ).order_by(Downtime_machines.date_start)

        analytics_by_machine = {}
        analytics_by_type = {}
        week_machine_data = {}
        week_type_data = {}

        def adjust_week_dates(start_of_week, end_of_week):
            if start_of_week.month != month:
                start_of_week = date(year, month, 1)
            if end_of_week.month != month:
                end_of_week = date(year, month, last_day_of_month)
            return start_of_week, end_of_week

        for machine_id, type_machine, type_id, total_downtime, downtime_date in results:
            total_downtime = total_downtime if total_downtime is not None else 0
            minutes = total_downtime // 60
            day_of_week = downtime_date.weekday()

            laser_machine = _ses.query(laser_park).filter(laser_park.id == machine_id).first()
            machine_names = laser_machine.get_laser_and_power_names() if laser_machine else str(machine_id)

            start_of_week = downtime_date - timedelta(days=downtime_date.weekday())
            end_of_week = start_of_week + timedelta(days=6)

            start_of_week, end_of_week = adjust_week_dates(start_of_week, end_of_week)

            week_key = f"{start_of_week.strftime('%d.%m.%y')} - {end_of_week.strftime('%d.%m.%y')}"

            week_machine_data.setdefault(week_key, {}).setdefault(machine_names, 0)
            week_machine_data[week_key][machine_names] += minutes

            week_type_data.setdefault(week_key, {}).setdefault(type_id, 0)
            week_type_data[week_key][type_id] += minutes

        for week, machines in week_machine_data.items():
            analytics_by_machine[week] = machines

        for week, types in week_type_data.items():
            analytics_by_type[week] = types

        return analytics_by_machine, analytics_by_type
    finally:
        _ses.close()


def get_downtime_analytics_by_machine(selected_date):

    # Определяем начало и конец месяца
    year = selected_date.year
    month = selected_date.month
    date_start = selected_date.replace(day=1) # Первый день месяца
    last_day_of_month = monthrange(year, month)[1] # Последний день месяца (вычисляем с помощью monthrange)
    date_end = selected_date.replace(day=last_day_of_month)

    _ses = create_db1()
    try:
        # Запрос к базе данных
        results = _ses.query(
            Downtime_machines.type_machine,
            Downtime_machines.machine_id,
            Downtime_machines.user_id,
            Downtime_machines.type_id,
            func.sum(func.timestampdiff(db.text('SECOND'), Downtime_machines.date_start, Downtime_machines.date_end)).label('total_downtime')
        ).outerjoin(
            laser_park, laser_park.id == Downtime_machines.machine_id
        ).filter(
            Downtime_machines.date_start >= date_start,
            Downtime_machines.date_start <= date_end,
            Downtime_machines.type_machine.in_(["Laser", "Bend"])  # можно добавить другие типы, например, "Bend"
        ).group_by(
            Downtime_machines.type_machine,
            Downtime_machines.machine_id,
            Downtime_machines.type_id
        ).order_by(
            func.sum(func.timestampdiff(db.text('SECOND'), Downtime_machines.date_start, Downtime_machines.date_end)).desc()
        )

        # Обработка результатов
        analytics = {}
        for type_machine, machine_id, user_id, type_id, total_downtime in results:

            total_downtime = total_downtime or 0
            minutes = total_downtime // 60

            if type_machine not in analytics:
                analytics[type_machine] = {}

            # Получаем имя машины
            if type_machine == 'Laser':
                laser_power = _ses.query(laser_park).filter(laser_park.id == machine_id).first()
                machine_names = laser_power.get_laser_and_power_names() if laser_power else machine_id
            elif type_machine == 'Bend':
                # machine_names = _ses.query(bend_park.name).filter(bend_park.id == machine_id).scalar()
                user_FIO = _ses.query(User.FIO).filter(User.id == user_id).scalar()
                machine_names = user_FIO
                machine_id = user_FIO
            if machine_id not in analytics[type_machine]:
                analytics[type_machine][machine_id] = {'name': machine_names, 'data': {}}

            analytics[type_machine][machine_id]['data'][type_id] = minutes
        return analytics
    finally:
        _ses.close()


def get_work_time_fund(month, year):
    work_hours_per_day = 8  # Количество рабочих часов в день
    current_day = date.today().day
    month_cal = calendar.monthcalendar(year, month)  # Получаем матрицу дней месяца
    # Подсчитываем количество рабочих дней, которые уже прошли (до текущего дня включительно)
    workdays_passed = sum(1 for week in month_cal for day in week[:5] if day != 0 and day <= current_day)  # [:5] для пн-пт
    time_fund_passed = workdays_passed * work_hours_per_day * 60  # Рабочие часы в минутах
    return time_fund_passed


def get_month_analytics_by_user(selected_date):

    month_ratio_by_laser = {}
    month_ratio_by_bend = {}

    # Определяем начало и конец месяца
    year = selected_date.year
    month = selected_date.month
    date_start = selected_date.replace(day=1) # Первый день месяца
    last_day_of_month = monthrange(year, month)[1] # Последний день месяца (вычисляем с помощью monthrange)
    date_end = selected_date.replace(day=last_day_of_month)

    TIME_FUND = get_work_time_fund(month, year)

    _ses = create_db1()

    try:
        # блок сбора данных по лазерным станкам
        _laser_list = _ses.query(Task_complete, laser_park).outerjoin(
            Task, Task.id == Task_complete.task_id).outerjoin(
            Laser_production, Laser_production.production_id == Task.production_id).outerjoin(
            laser_park, and_(laser_park.laser_id == Laser_production.laser_machine_id, laser_park.power_id == Laser_production.laser_power_id)).outerjoin(
            Production, Production.id == Task.production_id).filter(
            func.DATE(Task_complete.date_start) >= date_start,
            func.DATE(Task_complete.date_start) <= date_end,
            Task_complete.description != '-create_task',
            laser_park.laser_id != 4,
            Production.type_production_id == 4).order_by(
            Task_complete.date_start.desc()).all()

        for _tc, _lp in _laser_list:

            _time = (_tc.date_end - _tc.date_start).seconds if _tc.date_end else (datetime.datetime.now() - _tc.date_start).seconds
            _time = _time / 60
            laser_name = _lp.get_laser_and_power_names()

            # Инициализация словаря для операторов, если его еще нет
            if _tc.us.FIO not in month_ratio_by_laser:
                month_ratio_by_laser[_tc.us.FIO] = {'machines': {}}

            # Инициализация словаря для станков, если его еще нет
            if laser_name not in month_ratio_by_laser[_tc.us.FIO]['machines']:
                month_ratio_by_laser[_tc.us.FIO]['machines'][laser_name] = {
                    'all_work': 0.0, 'work': 0.0, 'setting': 0.0, 'sheet_loading': 0.0, 'downtime': 0.0, 'all': TIME_FUND
                }

            # Суммируем время по категориям для станка
            if _tc.description == '':
                month_ratio_by_laser[_tc.us.FIO]['machines'][laser_name]['work'] += _time
            elif _tc.description == '-sheet_loading':
                month_ratio_by_laser[_tc.us.FIO]['machines'][laser_name]['sheet_loading'] += _time
            elif _tc.description == '-setting':
                month_ratio_by_laser[_tc.us.FIO]['machines'][laser_name]['setting'] += _time
            month_ratio_by_laser[_tc.us.FIO]['machines'][laser_name]['all_work'] += _time
            month_ratio_by_laser[_tc.us.FIO]['machines'][laser_name]['all'] -= _time

        # блок сбора данных по гибочным станкам
        _bend_list = _ses.query(task_complete_bend).filter(
            func.DATE(task_complete_bend.date_s) >= date_start,
            func.DATE(task_complete_bend.date_e) <= date_end,
            ).order_by(
            task_complete_bend.date_s.desc()).all()
        
        for _tc in _bend_list:

            _time = (_tc.date_e - _tc.date_s).seconds if _tc.date_e else (datetime.datetime.now() - _tc.date_s).seconds
            _time = float(_time) / 60

            if _tc.us.FIO not in month_ratio_by_bend:
                month_ratio_by_bend[_tc.us.FIO] = {'work': 0.0, 'setting': 0.0, 'downtime': 0.0, 'all': TIME_FUND}

            # Суммируем время по категориям
            if _tc.description == '':
                month_ratio_by_bend[_tc.us.FIO]['work'] += _time
                month_ratio_by_bend[_tc.us.FIO]['all'] -= _time
            elif _tc.description == '-setting':
                month_ratio_by_bend[_tc.us.FIO]['setting'] += _time
                month_ratio_by_bend[_tc.us.FIO]['all'] -= _time

            
        _downtime_list = _ses.query(
            Downtime_machines,
            laser_park,
            func.sum(func.timestampdiff(db.text('SECOND'), Downtime_machines.date_start, Downtime_machines.date_end)).label('total_downtime')
        ).outerjoin(
            laser_park, laser_park.id == Downtime_machines.machine_id
        ).filter(
            Downtime_machines.date_start >= date_start,
            Downtime_machines.date_start <= date_end,
            Downtime_machines.type_machine.in_(["Laser", "Bend"])  # можно добавить другие типы, например, "Bend"
        ).group_by(
            Downtime_machines.type_machine,
            Downtime_machines.machine_id,
            Downtime_machines.user_id,
            Downtime_machines.type_id
        ).order_by(
            func.sum(func.timestampdiff(db.text('SECOND'), Downtime_machines.date_start, Downtime_machines.date_end)).desc()
        )

        # Обработка результатов
        for _dt, _lp, total_downtime in _downtime_list:
            if _dt.type_machine == 'Laser':
                laser_name = _lp.get_laser_and_power_names()

                if _dt.us.FIO not in month_ratio_by_laser:
                    month_ratio_by_laser[_dt.us.FIO] = {'machines': {}}

                if laser_name not in month_ratio_by_laser[_dt.us.FIO]['machines']:
                    month_ratio_by_laser[_dt.us.FIO]['machines'][laser_name] = {
                        'all_work': 0.0, 'work': 0.0, 'setting': 0.0, 'sheet_loading': 0.0, 'downtime': 0.0, 'all': TIME_FUND
                    }

                total_downtime = total_downtime or 0
                minutes = float(total_downtime) / 60
                month_ratio_by_laser[_dt.us.FIO]['machines'][laser_name]['downtime'] += minutes
                month_ratio_by_laser[_dt.us.FIO]['machines'][laser_name]['all'] -= minutes

            if _dt.type_machine == 'Bend':
                if _dt.us.FIO not in month_ratio_by_bend:
                    month_ratio_by_bend[_dt.us.FIO] = {'work': 0.0, 'setting': 0.0, 'downtime': 0.0, 'all': TIME_FUND}

                total_downtime = total_downtime or 0
                minutes = float(total_downtime) / 60

                month_ratio_by_bend[_dt.us.FIO]['downtime'] += minutes
                month_ratio_by_bend[_dt.us.FIO]['all'] -= minutes

        month_ratio_by_laser = {k: month_ratio_by_laser[k] for k in sorted(month_ratio_by_laser)} # Сначала сортируем пользователей
        for user, user_data in month_ratio_by_laser.items(): # Сортируем станки и обнуляем 'all', если нужно
            if 'machines' in user_data:
                user_data['machines'] = {machine: {**m, 'all': max(m['all'], 0)} 
                                        for machine, m in sorted(user_data['machines'].items())}

        month_ratio_by_bend = {k: month_ratio_by_bend[k] for k in sorted(month_ratio_by_bend)} 
        month_ratio_by_bend = {k: {**v, 'all': max(v['all'], 0)} for k, v in month_ratio_by_bend.items()} # если all меньше нуля - значит оператор нарезал больше чем фонд времни-обнуляем all для графика
        return month_ratio_by_laser, month_ratio_by_bend
    finally:
        _ses.close()


# дашборд мониторинга работы станков
@app.route('/dashboard_of_machines', methods=['GET'])
@login_required
def dashboard_of_machines():
    if not current_user.CheckAccess(14010):
        return json.dumps({'err':1, 'msg':'Вам недоступно!'})

    today = date.today()
    _current_time = time.mktime(datetime.datetime.now().timetuple())
    _timestamp_0800_today = time.mktime(datetime.datetime.combine(today, datetime.time(8, 0)).timetuple())
    _work_time = (_current_time - _timestamp_0800_today)

    _ses = create_db1()

    try:
        # блок сбора данных по лазерным станкам
        _laser_list = _ses.query(Task_complete, Laser_power, Laser_machine).outerjoin(
            Task, Task.id == Task_complete.task_id).outerjoin(
            Laser_production, Laser_production.production_id == Task.production_id).outerjoin(
            Laser_power, Laser_power.id == Laser_production.laser_power_id).outerjoin(
            Laser_machine, Laser_machine.id == Laser_production.laser_machine_id).outerjoin(
            Production, Production.id == Task.production_id).filter(
            func.DATE(Task_complete.date_start) == today,
            Task_complete.description != '-create_task',
            Laser_machine.id != 4,
            Production.type_production_id == 4).order_by(
            Task_complete.date_start.desc()).all()

        _laser_data = defaultdict(list)
        _laser_work_time_today = defaultdict(float)
        _laser_work_time_today_dict = defaultdict(lambda: defaultdict(float))

        for _tc, _lp, _lm in _laser_list:
            _laser_name = f"{_lm.name} {_lp.name}".strip()
            user_fio = _tc.us.FIO
            if _tc.description not in ['-setting', '-sheet_loading']:
                if _tc.date_end:
                    work_time_party = time.mktime(_tc.date_end.timetuple()) - time.mktime(_tc.date_start.timetuple())
                else:
                    work_time_party = _current_time - time.mktime(_tc.date_start.timetuple())
            else:
                work_time_party = 0
            _laser_work_time_today[_laser_name] += work_time_party
            _laser_work_time_today_dict[_laser_name][user_fio] += work_time_party

            _item = {
                # 'task_complete_id': _tc.id,
                'user_fio': _tc.us.FIO,
                'description': _tc.description,
                'ds': _tc.date_start.strftime('%d.%m.20%y %H:%M'),
                'de': _tc.date_end.strftime('%d.%m.20%y %H:%M') if _tc.date_end else '',
                'stamp_s': time.mktime(_tc.date_start.timetuple()),
                'stamp_e': time.mktime(_tc.date_end.timetuple()) if _tc.date_end else '',
                'work_time_party': work_time_party
            }
            _laser_data[_laser_name].append(_item)

        _laser_data = dict(_laser_data)
        _work_time_today = dict(_laser_work_time_today)
        _work_time_today_dict = {k: dict(v) for k, v in _laser_work_time_today_dict.items()}

        _laser_data_today = {k: (v, _work_time_today[k]) for k, v in _laser_data.items()}


        _laser_downtime_data = defaultdict(list)
        _laser_downtime_approved = defaultdict(list)
        _laser_downtime_today = defaultdict(float)

        _laser_downtime = _ses.query(Downtime_machines, Laser_machine, Laser_power).outerjoin(
            laser_park, laser_park.id == Downtime_machines.machine_id).outerjoin(
            Laser_machine, Laser_machine.id == laser_park.laser_id).outerjoin(
            Laser_power, Laser_power.id == laser_park.power_id).filter(
            Downtime_machines.type_machine == 'Laser',
            func.DATE(Downtime_machines.date_start) == today,
            )

        for _dt, _lm, _lp in _laser_downtime:
            _laser_name = f"{_lm.name} {_lp.name}".strip()
            if _dt.date_end:
                downtime_party = time.mktime(_dt.date_end.timetuple()) - time.mktime(_dt.date_start.timetuple())
            else:
                downtime_party = _current_time - time.mktime(_dt.date_start.timetuple())
            _laser_downtime_today[_laser_name] += downtime_party

            _item = {
                    'downtime_id': _dt.id,
                    'task_id': _dt.task_id if _dt.task_id else '',
                    'user_id': _dt.user_id,
                    'user_fio': _dt.us.FIO,
                    'ds': _dt.date_start.strftime('%H:%M'),
                    'de': _dt.date_end.strftime('%H:%M') if _dt.date_end else '',
                    'stamp_s': time.mktime(_dt.date_start.timetuple()),
                    'stamp_e': time.mktime(_dt.date_end.timetuple()) if _dt.date_end else '',
                    'type_id': _dt.type_id,
                    'description': _dt.description,
                    'reason': _dt.reason,
                    'downtime_party': downtime_party
                }
            if _dt.state != 'approved':
                _laser_downtime_data[_laser_name].append(_item)
            else:
                _laser_downtime_approved[_laser_name].append(_item)

        _laser_downtime_data = dict(_laser_downtime_data)
        _laser_downtime_approved = dict(_laser_downtime_approved)
        _downtime_today = dict(_laser_downtime_today)

        _laser = {}
        for key in _laser_data_today.keys():
            _laser[key] = {
                "data": _laser_data_today.get(key),
                "downtime_data": _laser_downtime_data.get(key),
                "downtime_approved": _laser_downtime_approved.get(key),
                "work_time_today": _work_time_today.get(key),
                "work_time_today_dict": _work_time_today_dict.get(key),
                "downtime_today": _downtime_today.get(key)
            }


        # блок сбора данных по гибочным станкам
        _bend_list = _ses.query(task_complete_bend, bend_park).outerjoin(
            bend_park, bend_park.id == task_complete_bend.bend_park_id).filter(
            func.DATE(task_complete_bend.date_s) == today).order_by(
            task_complete_bend.date_s.desc()).all()

        _bend_data = defaultdict(list)
        _bend_work_time_today = defaultdict(float)
        _bend_work_time_today_dict = defaultdict(lambda: defaultdict(float))
        for _tcb, _bp in _bend_list:
            _bend_name = _bp.name
            user_fio = _tcb.us.FIO

            if _tcb.description != '-setting':
                if _tcb.date_e:
                    work_time_party = time.mktime(_tcb.date_e.timetuple()) - time.mktime(_tcb.date_s.timetuple())
                else:
                    work_time_party = _current_time - time.mktime(_tcb.date_s.timetuple())
            else:
                work_time_party = 0
            _bend_work_time_today[_bend_name] += work_time_party
            _bend_work_time_today_dict[_bend_name][user_fio] += work_time_party

            _item = {
                'user_fio': _tcb.us.FIO,
                'description': _tcb.description,
                'ds': _tcb.date_s.strftime('%d.%m.20%y %H:%M'),
                'de': _tcb.date_e.strftime('%d.%m.20%y %H:%M') if _tcb.date_e else '',
                'stamp_s': time.mktime(_tcb.date_s.timetuple()),
                'stamp_e': time.mktime(_tcb.date_e.timetuple()) if _tcb.date_e else '',
                'work_time_party': work_time_party
            }
            _bend_data[_bend_name].append(_item)

        _bend_data = dict(_bend_data)
        _work_time_today = dict(_bend_work_time_today)
        _bend_data_today = {k: (v, _work_time_today[k]) for k, v in _bend_data.items()}
        _work_time_today_dict = {k: dict(v) for k, v in _bend_work_time_today_dict.items()}

        _bend_downtime_data = defaultdict(list)
        _bend_downtime_approved = defaultdict(list)
        _bend_downtime_today = defaultdict(float)

        _bend_downtime = _ses.query(Downtime_machines, bend_park).outerjoin(
            bend_park, bend_park.id == Downtime_machines.machine_id).filter(
            Downtime_machines.type_machine == 'Bend',
            func.DATE(Downtime_machines.date_start) == today,
            )

        for _dt, _bp in _bend_downtime:
            _bend_name = _bp.name
            if _dt.date_end:
                downtime_party = time.mktime(_dt.date_end.timetuple()) - time.mktime(_dt.date_start.timetuple())
            else:
                downtime_party = _current_time - time.mktime(_dt.date_start.timetuple())
            _bend_downtime_today[_bend_name] += downtime_party

            _item = {
                    'downtime_id': _dt.id,
                    'task_id': _dt.task_id if _dt.task_id else '',
                    'user_id': _dt.user_id,
                    'user_fio': _dt.us.FIO,
                    'ds': _dt.date_start.strftime('%H:%M'),
                    'de': _dt.date_end.strftime('%H:%M') if _dt.date_end else '',
                    'stamp_s': time.mktime(_dt.date_start.timetuple()),
                    'stamp_e': time.mktime(_dt.date_end.timetuple()) if _dt.date_end else '',
                    'type_id': _dt.type_id,
                    'description': _dt.description,
                    'reason': _dt.reason,
                    'downtime_party': downtime_party
                }
            if _dt.state != 'approved':
                _bend_downtime_data[_bend_name].append(_item)
            else:
                _bend_downtime_approved[_bend_name].append(_item)

        _bend_downtime_data = dict(_bend_downtime_data)
        _bend_downtime_approved = dict(_bend_downtime_approved)
        _downtime_today = dict(_bend_downtime_today)

        _bend = {}
        for key in _bend_data_today.keys():
            _bend[key] = {
                "data": _bend_data_today.get(key),
                "downtime_data": _bend_downtime_data.get(key),
                "downtime_approved": _bend_downtime_approved.get(key),
                "work_time_today": _work_time_today.get(key),
                "work_time_today_dict": _work_time_today_dict.get(key),
                "downtime_today": _downtime_today.get(key)
            }


        # блок сбора данных по токарно-фрезерным станкам
        _turner_list = _ses.query(Task_complete).outerjoin(
            Task, Task.id == Task_complete.task_id).outerjoin(
            Production, Production.id == Task.production_id).filter(
            func.DATE(Task_complete.date_start) == today,
            Task_complete.description != '-create_task',
            Production.type_production_id == 2).order_by(
            Task_complete.date_start.desc()).all()

        _turner_data = defaultdict(list)
        _turner_work_time_today = defaultdict(float)

        for _tc in _turner_list:
            _turner_name = _tc.us.FIO

            if _tc.description == 'Завершена операция' or _tc.description == '':
                if _tc.date_end:
                    work_time_party = time.mktime(_tc.date_end.timetuple()) - time.mktime(_tc.date_start.timetuple())
                else:
                    work_time_party = _current_time - time.mktime(_tc.date_start.timetuple())
            else:
                work_time_party = 0
            _turner_work_time_today[_turner_name] += work_time_party

            _item = {
                # 'task_complete_id': _tcb.id,
                # 'user_id': _tc.user_id,
                # 'description': _tc.description,    # у токарей нет НАСТРОЙКИ!!! (добавить?)
                'ds': _tc.date_start.strftime('%d.%m.20%y %H:%M'),
                'de': _tc.date_end.strftime('%d.%m.20%y %H:%M') if _tc.date_end else '',
                'stamp_s': time.mktime(_tc.date_start.timetuple()),
                'stamp_e': time.mktime(_tc.date_end.timetuple()) if _tc.date_end else '',
            }
            _turner_data[_turner_name].append(_item)
        _turner_data = dict(_turner_data)
        _work_time_today = dict(_turner_work_time_today)
        _turner_data_today = {k: (v, _work_time_today[k]) for k, v in _turner_data.items()}

        # блок сбора данных по покраске
        _paint_list = _ses.query(Logs).filter(func.DATE(Logs.datetime) == today, Logs.type == 1020, Logs.user_id == 100).order_by(Logs.datetime.desc()).all()
        _paint_data = defaultdict(list)
        _count_paint = 0
        if _paint_list:
            for _l in _paint_list:
                _paint_name = 'Малярка'
                _item = {
                    'description': _l.description,    # в ней tchs.id/tchs.prod_id
                    'de': _l.datetime.strftime('%d.%m.20%y %H:%M'),
                    'stamp_e': time.mktime(_l.datetime.timetuple()),
                }
                _paint_data[_paint_name].append(_item)
            _paint_data = dict(_paint_data)
            _count_paint = len(_paint_data['Малярка'])

        # блок сбора данных по настройкам разрешенного времни простоя
        settings_downtime = _ses.query(settings_main.value).filter(settings_main.name == 'settings_downtime').first()
        if settings_downtime:
            downtime_values = settings_downtime.value.split(',')
            if len(downtime_values) == 2:
                downtime1 = int(downtime_values[0].strip())
                downtime2 = int(downtime_values[1].strip())
                _settings = (downtime1, downtime2)
        else:
            _settings_downtime = settings_main(name='settings_downtime', value=', '.join([str(30), str(60)]))
            _ses.add(_settings_downtime)
            _ses.commit()
            _settings = (30, 60)

        allowed_downtime_value = _ses.query(settings_main.value).filter(settings_main.name == 'allowed_downtime').scalar()
        _allowed_downtime = int(allowed_downtime_value) if allowed_downtime_value is not None else 120

        current_month = date.today().replace(day=1)  # берем текущий месяц
        downtime_analytics_by_machine = get_downtime_analytics_by_machine(current_month)
        weekly_downtime_by_machine, weekly_downtime_by_type = get_weekly_downtime(current_month)
        month_ratio_by_laser, month_ratio_by_bend = get_month_analytics_by_user(current_month)

        month_names = [
            "январь", "февраль", "март", "апрель", "май", "июнь",
            "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
        ]

        current_month_number = current_month.month
        current_month_name = month_names[current_month_number - 1]
        current_year = current_month.year

        current_month = {
            "month_name": current_month_name,
            "month_number": current_month_number,
            'current_year': current_year
        }

        return render_template('dashboard_of_machines.html', current_time =_current_time,
                               settings_downtime =_settings,
                               work_time=_work_time,
                               allowed_downtime =_allowed_downtime,
                               laser =_laser,
                               bend =_bend,
                               turner_data_today =_turner_data_today,
                               paint_data =_paint_data,
                               count_paint =_count_paint,
                               downtime_analytics_by_machine = downtime_analytics_by_machine,
                               weekly_downtime_by_type = weekly_downtime_by_type,
                               weekly_downtime_by_machine = weekly_downtime_by_machine,
                               month_ratio_by_laser = month_ratio_by_laser, 
                               month_ratio_by_bend = month_ratio_by_bend,
                               current_month = current_month
                               )
    finally:
        _ses.close()

@app.route('/save_settings_downtime', methods=['POST'])
@login_required
def save_settings_downtime():
    if not current_user.CheckAccess(14010):
        return json.dumps({'err':1, 'msg':'Вам недоступно!'})
    data = request.get_json()
    downtime1 = data.get('downtime1')
    downtime2 = data.get('downtime2')
    _allowed_downtime_new = data.get('allowed_downtime')

    _ses = create_db1()

    try:
        _settings_downtime = _ses.query(settings_main).filter(settings_main.name == 'settings_downtime').first()
        _allowed_downtime = _ses.query(settings_main).filter(settings_main.name == 'allowed_downtime').first()

        if _settings_downtime:
            _settings_downtime.value = ', '.join([downtime1, downtime2])
        else:
            _settings_downtime = settings_main(name='settings_downtime', value=', '.join([downtime1, downtime2]))
            _ses.add(_settings_downtime)
        _ses.commit()

        if _allowed_downtime:
            _allowed_downtime.value = _allowed_downtime_new
        else:
            _allowed_downtime = settings_main(name='allowed_downtime', value=_allowed_downtime_new)
            _ses.add(_allowed_downtime)
        _ses.commit()


        return jsonify({'message': 'настройки обновлены'})
    finally:
        _ses.close()


@app.route('/add_new_type_downtime', methods=['POST'])
@login_required
def add_new_type_downtime():
    data = request.get_json()
    _new_type_dt = data.get('new_type_dt')
    _type_maсhine = data.get('type_maсhine')
    _state = 'actual'
    _ses = create_db1()

    try:
        _new_type_downtime = Downtime_types(_type_maсhine, _new_type_dt, _state)
        _ses.add(_new_type_downtime)
        _ses.commit()
        return jsonify({'message': 'настройки обновлены'})
    finally:
        _ses.close()


@app.route('/get_machine_downtime_types', methods=['GET'])
@login_required
def get_machine_downtime_types():
    _ses = create_db1()
    downtime_dict = {}
    try:
        _downtime_arr = _ses.query(Downtime_types).filter(Downtime_types.state == 'actual').all()

        for downtime in _downtime_arr:
            machine_type = downtime.type_machine
            downtime_name = downtime.name
            if machine_type not in downtime_dict:
                downtime_dict[machine_type] = []
            downtime_dict[machine_type].append(downtime_name)
        return jsonify(downtime_dict)
    finally:
        _ses.close()


@app.route('/delete_downtime_type', methods=['POST'])
@login_required
def delete_downtime_type():
    data = request.get_json()
    machine_type = data.get('machine_type')
    downtime_type = data.get('downtime_type')
    _ses = create_db1()
    try:
        downtime_record = _ses.query(Downtime_types).filter_by(type_machine=machine_type, name=downtime_type, state='actual').first()
        if downtime_record:
            downtime_record.state = 'not relevant'
            _ses.commit()
            return jsonify({'message': 'Тип простоя обновлен'}), 200
        else:
            return jsonify({'message': 'Запись не найдена'}), 404
    finally:
        _ses.close()


# дашборд мониторинга работы станков с выбором даты
@app.route('/dashboard_of_machines_2', methods=['GET'])
@login_required
def dashboard_of_machines_2():
    if not current_user.CheckAccess(14010):
        return json.dumps({'err':1, 'msg':'Вам недоступно!'})
    selected_date = request.args.get('date')
    _current_time = time.mktime(datetime.datetime.now().timetuple())
    _current_day = selected_date == date.today().strftime('%Y-%m-%d')

    today = date.today()
    if _current_day:
        _timestamp_0800_today = time.mktime(datetime.datetime.combine(today, datetime.time(8, 0)).timetuple())
        _work_time = (_current_time - _timestamp_0800_today)
    else:
        _work_time = 28800 # 8 часовая смена  из условия что за одним станком пока один оператор всего лишь

    _ses = create_db1()
    try:
        # блок сбора данных по лазерным станкам
        _laser_list = _ses.query(Task_complete, Laser_power, Laser_machine).outerjoin(
            Task, Task.id == Task_complete.task_id).outerjoin(
            Laser_production, Laser_production.production_id == Task.production_id).outerjoin(
            Laser_power, Laser_power.id == Laser_production.laser_power_id).outerjoin(
            Laser_machine, Laser_machine.id == Laser_production.laser_machine_id).outerjoin(
            Production, Production.id == Task.production_id).filter(
            func.DATE(Task_complete.date_start) == selected_date,
            Task_complete.description != '-create_task',
            Laser_machine.id != 4,
            Production.type_production_id == 4).order_by(
            Task_complete.date_start.desc()).all()

        _laser_data = defaultdict(list)
        _laser_work_time_today = defaultdict(float)
        _laser_work_time_today_dict = defaultdict(lambda: defaultdict(float))

        for _tc, _lp, _lm in _laser_list:
            _laser_name = f"{_lm.name} {_lp.name}".strip()

            if _tc.description not in ['-setting', '-sheet_loading']:
                if _tc.date_end:
                    work_time_party = time.mktime(_tc.date_end.timetuple()) - time.mktime(_tc.date_start.timetuple())
                else:
                    work_time_party = _current_time - time.mktime(_tc.date_start.timetuple())
            else:
                work_time_party = 0
            _laser_work_time_today[_laser_name] += work_time_party
            user_fio = _tc.us.FIO if _tc.us else ''
            _laser_work_time_today_dict[_laser_name][user_fio] += work_time_party

            _item = {
                # 'task_complete_id': _tc.id,
                'user_fio': user_fio,
                'description': _tc.description,
                'ds': _tc.date_start.strftime('%d.%m.20%y %H:%M'),
                'de': _tc.date_end.strftime('%d.%m.20%y %H:%M') if _tc.date_end else '',
                'stamp_s': time.mktime(_tc.date_start.timetuple()),
                'stamp_e': time.mktime(_tc.date_end.timetuple()) if _tc.date_end else '',
                'work_time_party': work_time_party
            }
            _laser_data[_laser_name].append(_item)

        _laser_data = dict(_laser_data)
        _work_time_today = dict(_laser_work_time_today)
        _work_time_today_dict = {k: dict(v) for k, v in _laser_work_time_today_dict.items()}

        _laser_data_today = {k: (v, _work_time_today[k]) for k, v in _laser_data.items()}

        _laser_downtime_data = defaultdict(list)
        _laser_downtime_approved = defaultdict(list)
        _laser_downtime_today = defaultdict(float)

        _laser_downtime = _ses.query(Downtime_machines, Laser_machine, Laser_power).outerjoin(
            laser_park, laser_park.id == Downtime_machines.machine_id).outerjoin(
            Laser_machine, Laser_machine.id == laser_park.laser_id).outerjoin(
            Laser_power, Laser_power.id == laser_park.power_id).filter(
            Downtime_machines.type_machine == 'Laser',
            func.DATE(Downtime_machines.date_start) == selected_date,
            )

        for _dt, _lm, _lp in _laser_downtime:
            _laser_name = f"{_lm.name} {_lp.name}".strip()
            if _dt.date_end:
                downtime_party = time.mktime(_dt.date_end.timetuple()) - time.mktime(_dt.date_start.timetuple())
            else:
                downtime_party = _current_time - time.mktime(_dt.date_start.timetuple())
            _laser_downtime_today[_laser_name] += downtime_party

            _item = {
                    'downtime_id': _dt.id,
                    'task_id': _dt.task_id if _dt.task_id else '',
                    'user_id': _dt.user_id,
                    'user_fio': _tc.us.FIO if _tc.us else '',
                    'ds': _dt.date_start.strftime('%H:%M'),
                    'de': _dt.date_end.strftime('%H:%M') if _dt.date_end else '',
                    'stamp_s': time.mktime(_dt.date_start.timetuple()),
                    'stamp_e': time.mktime(_dt.date_end.timetuple()) if _dt.date_end else '',
                    'type_id': _dt.type_id,
                    'description': _dt.description,
                    'reason': _dt.reason,
                    'downtime_party': downtime_party
                }
            if _dt.state != 'approved':
                _laser_downtime_data[_laser_name].append(_item)
            else:
                _laser_downtime_approved[_laser_name].append(_item)

        _laser_downtime_data = dict(_laser_downtime_data)
        _laser_downtime_approved = dict(_laser_downtime_approved)
        _downtime_today = dict(_laser_downtime_today)

        _laser = {}
        for key in _laser_data_today.keys():
            _laser[key] = {
                "data": _laser_data_today.get(key),
                "downtime_data": _laser_downtime_data.get(key),
                "downtime_approved": _laser_downtime_approved.get(key),
                "work_time_today": _work_time_today.get(key),
                "work_time_today_dict": _work_time_today_dict.get(key),
                "downtime_today": _downtime_today.get(key),
                # "downtime_analytics_by_machine": _downtime_analytics.get(key),
            }


        # блок сбора данных по гибочным станкам
        _bend_list = _ses.query(task_complete_bend, bend_park).outerjoin(
            bend_park, bend_park.id == task_complete_bend.bend_park_id).filter(
            func.DATE(task_complete_bend.date_s) == selected_date).order_by(
            task_complete_bend.date_s.desc()).all()

        _bend_data = defaultdict(list)
        _bend_work_time_today = defaultdict(float)
        _bend_work_time_today_dict = defaultdict(lambda: defaultdict(float))
        for _tcb, _bp in _bend_list:
            if _bp is None:
                _bend_name = '-'
            else:
                _bend_name = _bp.name

            if _tcb.description != '-setting':
                if _tcb.date_e:
                    work_time_party = time.mktime(_tcb.date_e.timetuple()) - time.mktime(_tcb.date_s.timetuple())
                else:
                    work_time_party = _current_time - time.mktime(_tcb.date_s.timetuple())
            else:
                work_time_party = 0
            _bend_work_time_today[_bend_name] += work_time_party

            user_fio = _tcb.us.FIO if _tcb.us else ''
            _bend_work_time_today_dict[_bend_name][user_fio] += work_time_party

            _item = {
                # 'task_complete_id': _tcb.id,
                'user_fio': user_fio,
                'description': _tcb.description,
                'ds': _tcb.date_s.strftime('%d.%m.20%y %H:%M'),
                'de': _tcb.date_e.strftime('%d.%m.20%y %H:%M') if _tcb.date_e else '',
                'stamp_s': time.mktime(_tcb.date_s.timetuple()),
                'stamp_e': time.mktime(_tcb.date_e.timetuple()) if _tcb.date_e else '',
                'work_time_party': work_time_party
            }
            _bend_data[_bend_name].append(_item)

        _bend_data = dict(_bend_data)
        _work_time_today = dict(_bend_work_time_today)
        _bend_data_today = {k: (v, _work_time_today[k]) for k, v in _bend_data.items()}
        _work_time_today_dict = {k: dict(v) for k, v in _bend_work_time_today_dict.items()}

        _bend_downtime_data = defaultdict(list)
        _bend_downtime_approved = defaultdict(list)
        _bend_downtime_today = defaultdict(float)

        _bend_downtime = _ses.query(Downtime_machines, bend_park).outerjoin(
            bend_park, bend_park.id == Downtime_machines.machine_id).filter(
            Downtime_machines.type_machine == 'Bend',
            func.DATE(Downtime_machines.date_start) == selected_date,
            )

        for _dt, _bp in _bend_downtime:
            if _bp is None:
                _bend_name = '-'
            else:
                _bend_name = _bp.name
            if _dt.date_end:
                downtime_party = time.mktime(_dt.date_end.timetuple()) - time.mktime(_dt.date_start.timetuple())
            else:
                downtime_party = _current_time - time.mktime(_dt.date_start.timetuple())
            _bend_downtime_today[_bend_name] += downtime_party

            _item = {
                    'downtime_id': _dt.id,
                    'task_id': _dt.task_id if _dt.task_id else '',
                    'user_id': _dt.user_id,
                    'user_fio': _tc.us.FIO if _tc.us else '',
                    'ds': _dt.date_start.strftime('%H:%M'),
                    'de': _dt.date_end.strftime('%H:%M') if _dt.date_end else '',
                    'stamp_s': time.mktime(_dt.date_start.timetuple()),
                    'stamp_e': time.mktime(_dt.date_end.timetuple()) if _dt.date_end else '',
                    'type_id': _dt.type_id,
                    'description': _dt.description,
                    'reason': _dt.reason,
                    'downtime_party': downtime_party
                }
            if _dt.state != 'approved':
                _bend_downtime_data[_bend_name].append(_item)
            else:
                _bend_downtime_approved[_bend_name].append(_item)

        _bend_downtime_data = dict(_bend_downtime_data)
        _bend_downtime_approved = dict(_bend_downtime_approved)
        _downtime_today = dict(_bend_downtime_today)

        _bend = {}
        for key in _bend_data_today.keys():
            _bend[key] = {
                "data": _bend_data_today.get(key),
                "downtime_data": _bend_downtime_data.get(key),
                "downtime_approved": _bend_downtime_approved.get(key),
                "work_time_today": _work_time_today.get(key),
                "work_time_today_dict": _work_time_today_dict.get(key),
                "downtime_today": _downtime_today.get(key)
            }


        # блок сбора данных по токарно-фрезерным станкам
        _turner_list = _ses.query(Task_complete).outerjoin(
            Task, Task.id == Task_complete.task_id).outerjoin(
            Production, Production.id == Task.production_id).filter(
            func.DATE(Task_complete.date_start) == selected_date,
            Task_complete.description != '-create_task',
            Production.type_production_id == 2).order_by(
            Task_complete.date_start.desc()).all()

        _turner_data = defaultdict(list)
        _turner_work_time_today = defaultdict(float)

        for _tc in _turner_list:
            _turner_name = _tc.us.FIO if _tc.us else ''

            if _tc.description == 'Завершена операция' or _tc.description == '':
                if _tc.date_end:
                    work_time_party = time.mktime(_tc.date_end.timetuple()) - time.mktime(_tc.date_start.timetuple())
                else:
                    work_time_party = _current_time - time.mktime(_tc.date_start.timetuple())
            else:
                work_time_party = 0
            _turner_work_time_today[_turner_name] += work_time_party

            _item = {
                # 'task_complete_id': _tcb.id,
                # 'user_id': _tc.user_id,
                # 'description': _tc.description,    # у токарей нет НАСТРОЙКИ!!! (добавить?)
                'ds': _tc.date_start.strftime('%d.%m.20%y %H:%M'),
                'de': _tc.date_end.strftime('%d.%m.20%y %H:%M') if _tc.date_end else '',
                'stamp_s': time.mktime(_tc.date_start.timetuple()),
                'stamp_e': time.mktime(_tc.date_end.timetuple()) if _tc.date_end else '',
            }
            _turner_data[_turner_name].append(_item)
        _turner_data = dict(_turner_data)
        _work_time_today = dict(_turner_work_time_today)
        _turner_data_today = {k: (v, _work_time_today[k]) for k, v in _turner_data.items()}

        # блок сбора данных по покраске
        _paint_list = _ses.query(Logs).filter(func.DATE(Logs.datetime) == selected_date, Logs.type == 1020, Logs.user_id == 100).order_by(Logs.datetime.desc()).all()
        _paint_data = defaultdict(list)
        _count_paint = 0
        if _paint_list:
            for _l in _paint_list:
                _paint_name = 'Малярка'
                _item = {
                    'description': _l.description,    # в ней tchs.id/tchs.prod_id
                    'de': _l.datetime.strftime('%d.%m.20%y %H:%M'),
                    'stamp_e': time.mktime(_l.datetime.timetuple()),
                }
                _paint_data[_paint_name].append(_item)
            _paint_data = dict(_paint_data)
            _count_paint = len(_paint_data['Малярка'])
        settings_downtime = _ses.query(settings_main.value).filter(settings_main.name == 'settings_downtime').first()
        if settings_downtime:
            downtime_values = settings_downtime.value.split(',')
            if len(downtime_values) == 2:
                downtime1 = int(downtime_values[0].strip())
                downtime2 = int(downtime_values[1].strip())
                _settings = (downtime1, downtime2)
        else:
            _settings_downtime = settings_main(name='settings_downtime', value=', '.join([str(30), str(60)]))
            _ses.add(_settings_downtime)
            _ses.commit()
            _settings = (30, 60)

        return render_template('dashboard_of_machines_info.html',
                            settings_downtime=_settings,
                            current_time=_current_time,
                            current_day=_current_day,
                            work_time=_work_time,
                            laser=_laser,
                            bend=_bend,
                            turner_data_today=_turner_data_today,
                            paint_data=_paint_data,
                            count_paint=_count_paint)
    finally:
        _ses.close()


@app.route('/dashboard_of_machines_charts', methods=['GET'])
@login_required
def dashboard_of_machines_charts():
    if not current_user.CheckAccess(14010):
        return json.dumps({'err': 1, 'msg': 'Вам недоступно!'})

    _ses = create_db1()
    try:
        selected_year = request.args.get('year')
        selected_month = request.args.get('month')
        month_names = [
            "январь", "февраль", "март", "апрель", "май", "июнь",
            "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
        ]

        if selected_year and selected_month:
            current_month_name = month_names[int(selected_month) - 1]
            current_month_number = selected_month
            current_year = selected_year
            selected_date = date.fromisoformat(f"{selected_year}-{selected_month}-01")
        else:
            current_month_name = month_names[selected_date.month - 1]
            current_month_number = selected_date.month
            current_year = selected_date.year
            selected_date = date.today().replace(day=1) 

        current_month = {
            "month_name": current_month_name,
            "month_number":current_month_number,
            'current_year': current_year
        }

        downtime_analytics_by_machine = get_downtime_analytics_by_machine(selected_date)
        weekly_downtime_by_machine, weekly_downtime_by_type = get_weekly_downtime(selected_date)
        month_ratio_by_laser, month_ratio_by_bend = get_month_analytics_by_user(selected_date)

        return jsonify({
            'html': render_template(
                'dashboard_of_machines_charts.html',
                downtime_analytics_by_machine=downtime_analytics_by_machine,
                weekly_downtime_by_type=weekly_downtime_by_type,
                weekly_downtime_by_machine=weekly_downtime_by_machine,
                month_ratio_by_laser = month_ratio_by_laser,
                month_ratio_by_bend = month_ratio_by_bend,
                current_month = current_month
            ),
            'downtime_analytics_by_machine': downtime_analytics_by_machine,
            'weekly_downtime_by_machine': weekly_downtime_by_machine,
            'weekly_downtime_by_type': weekly_downtime_by_type,
            'month_ratio_by_laser': month_ratio_by_laser,
            'month_ratio_by_bend': month_ratio_by_bend,
            'current_month': current_month
        })
    finally:
        _ses.close()
