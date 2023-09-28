from datetime import datetime
from hashlib import md5
from time import time
from flask import current_app, url_for
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from app import db, login
import json
import redis
import rq

# Таблица подписчиков
followers = db.Table(
    'followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)

# schedule_table = db.Table('schedule', db.Model.metadata,
#     db.Column('left_id', db.Integer, db.ForeignKey('left.id')),
#     db.Column('right_id', db.Integer, db.ForeignKey('right.id'))
# )
#
# class ScheduleHelper(db.Model):
#     __tablename__ = 'left'
#     id = db.Column(db.Integer, primary_key=True)
#     children = db.relationship("DayOfTheWeek",
#                     secondary=schedule_table)
#
# class DayOfTheWeek(db.Model):
#     __tablename__ = 'right'
#     id = db.Column(db.Integer, primary_key=True)

schedule = db.Table('schedule', db.Model.metadata,
    db.Column('schedule_helper_id', db.Integer, db.ForeignKey('schedule_helper.id')),
    db.Column('day_of_the_week_id', db.Integer, db.ForeignKey('day_of_the_week.id')),
    db.Column('evenness_id', db.Integer, db.ForeignKey('evenness.id')),
    db.Column('couple_id', db.Integer, db.ForeignKey('couple.id')),
    db.Column('group_id', db.Integer, db.ForeignKey('group.id')),
    db.Column('discipline_id', db.Integer, db.ForeignKey('discipline.id')),
    db.Column('auditory_id', db.Integer, db.ForeignKey('auditory.id')),
)


class ScheduleHelper(db.Model):
    __tablename__ = 'schedule_helper'
    id = db.Column(db.Integer, primary_key=True)
    day_of_the_week = db.relationship('DayOfTheWeek', secondary=schedule)
    evenness = db.relationship('Evenness', secondary=schedule)
    couple = db.relationship('Couple', secondary=schedule)
    group = db.relationship('Group', secondary=schedule)
    discipline = db.relationship('Discipline', secondary=schedule)
    auditory = db.relationship('Auditory', secondary=schedule)

    def __repr__(self):
        return f'Schedule "{self.day_of_the_week}"'


class DayOfTheWeek(db.Model):
    __tablename__ = 'day_of_the_week'
    id = db.Column(db.Integer, primary_key=True)
    day_of_the_week = db.Column(db.String(16))

    def __repr__(self):
        return f'<Day of the week "{self.day_of_the_week}">'


class Evenness(db.Model):
    __tablename__ = 'evenness'
    id = db.Column(db.Integer, primary_key=True)
    weeks = db.Column(db.String(5))
    evenness = db.Column(db.String(5))

    def __repr__(self):
        return f'''<
        Weeks "{self.weeks}"
        Evenness "{self.evenness}">'''


class Couple(db.Model):
    __tablename__ = 'couple'
    id = db.Column(db.Integer, primary_key=True)
    couple = db.Column(db.Integer)

    def __repr__(self):
        return f'''<
         Couple:
         "{self.couple}">'''


class Group(db.Model):
    __tablename__ = 'group'
    id = db.Column(db.Integer, primary_key=True)
    group = db.Column(db.String(32))

    def __repr__(self):
        return f'<Group "{self.group}">'


class Discipline(db.Model):
    __tablename__ = 'discipline'
    id = db.Column(db.Integer, primary_key=True)
    discipline = db.Column(db.String(32))

    def __repr__(self):
        return f'<Discipline "{self.discipline}">'


class Auditory(db.Model):
    __tablename__ = 'auditory'
    id = db.Column(db.Integer, primary_key=True)
    auditory = db.Column(db.String(10))

    def __repr__(self):
        return f'<Auditory "{self.auditory}">'


# Класс для операций с пользователем
class User(UserMixin, db.Model):
    # Разные значения пользователя
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    about_me = db.Column(db.String(140))
    last_seen = (db.Column(db.DateTime, default=datetime.utcnow))
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')
    notifications = db.relationship('Notification', backref='user',
                                    lazy='dynamic')
    tasks = db.relationship('Task', backref='user', lazy='dynamic')

    def __repr__(self):
        return '<User "{}">'.format(self.username)

    # Установить пароль
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    # Проверить пароль
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Получаем аватар с заданным размером по email пользователя
    def avatar(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(
            digest, size)

    # Подписка пользователя
    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    # Отписка пользователя
    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    # Подписан ли пользователь
    def is_following(self, user):
        return self.followed.filter(
            followers.c.followed_id == user.id).count() > 0

    def followed_posts(self):
        followed = Post.query.join(
            followers, (followers.c.followed_id == Post.user_id)).filter(
            followers.c.follower_id == self.id)  # посты тех, на кого подписался
        own = Post.query.filter_by(user_id=self.id)  # посты самого пользователя
        return followed.union(own).order_by(Post.timestamp.desc())  # объединение и сортировка

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            current_app.config['SECRET_KEY'], algorithm='HS256')

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
        except:
            return
        return User.query.get(id)

    def add_notification(self, name, data):
        self.notifications.filter_by(name=name).delete()
        n = Notification(name=name, payload_json=json.dumps(data), user=self)
        db.session.add(n)
        return n

    def launch_task(self, name, description, *args, **kwargs):
        rq_job = current_app.task_queue.enqueue('app.tasks.' + name, self.id,
                                                *args, **kwargs)
        task = Task(id=rq_job.get_id(), name=name, description=description,
                    user=self)
        db.session.add(task)
        return task

    def get_tasks_in_progress(self):
        return Task.query.filter_by(user=self, complete=False).all()

    def get_task_in_progress(self, name):
        return Task.query.filter_by(name=name, user=self,
                                    complete=False).first()

    def to_dict(self, include_email=False):
        data = {
            'id': self.id,
            'username': self.username,
            'last_seen': self.last_seen.isoformat() + 'Z',
            'about_me': self.about_me,
            'post_count': self.posts.count(),
            'follower_count': self.followers.count(),
            'followed_count': self.followed.count(),
            '_links': {
                'self': url_for('api.get_user', id=self.id),
                'followers': url_for('api.get_followers', id=self.id),
                'followed': url_for('api.get_followed', id=self.id),
                'avatar': self.avatar(128)
            }
        }
        if include_email:
            data['email'] = self.email
        return data

    def from_dict(self, data, new_user=False):
        for field in ['username', 'email', 'about_me']:
            if field in data:
                setattr(self, field, data[field])
        if new_user and 'password' in data:
            self.set_password(data['password'])


# Класс для операций с постами
class Post(db.Model):
    # Разные значения поста
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(140))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __repr__(self):
        return '<Post "{}">'.format(self.body)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.Float, index=True, default=time)
    payload_json = db.Column(db.Text)

    def get_data(self):
        return json.loads(str(self.payload_json))


class Task(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(128), index=True)
    description = db.Column(db.String(128))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    complete = db.Column(db.Boolean, default=False)

    def get_rq_job(self):
        try:
            rq_job = rq.job.Job.fetch(self.id, connection=current_app.redis)
        except (redis.exceptions.RedisError, rq.exceptions.NoSuchJobError):
            return None
        return rq_job

    def get_progress(self):
        job = self.get_rq_job()
        return job.meta.get('progress', 0) if job is not None else 100


@login.user_loader
def load_user(id):
    return User.query.get(int(id))
