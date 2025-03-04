from sqlalchemy import Column, Date, DateTime, Integer, String, Unicode, ForeignKey, UniqueConstraint, Text, UnicodeText
from sqlalchemy.orm import relationship, backref
from flask_login import UserMixin
from sqlalchemy.sql.expression import desc
from .database import Base
import datetime as dt
from pytz import timezone

central = timezone('US/Central')

class CoderArticleAnnotation(Base):
    __tablename__ = 'coder_article_annotation'
    id         = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('article_metadata.id'), nullable = False)
    variable   = Column(String(100), nullable = False)
    value      = Column(Text, nullable = False)
    text       = Column(UnicodeText)
    coder_id   = Column(Integer, ForeignKey('user.id'))
    timestamp  = Column(DateTime)

    def __init__(self, article_id, variable, value, coder_id, text = None):
        self.article_id = article_id
        self.variable   = variable
        self.value      = value
        self.text       = text
        self.coder_id   = coder_id
        self.timestamp  = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<CoderArticleAnnotation %r>' % (self.id)


class CanonicalEvent(Base):
    __tablename__ = 'canonical_event'
    id           = Column(Integer, primary_key=True)
    coder_id     = Column(Integer, ForeignKey('user.id'), nullable = False)
    key          = Column(Text, nullable = False)
    description  = Column(UnicodeText, nullable = False)
    notes        = Column(UnicodeText)
    last_updated = Column(DateTime)

    UniqueConstraint('key', name = 'unique1')

    def __init__(self, coder_id, key, description, notes = None):
        self.coder_id     = coder_id
        self.key          = key
        self.description  = description,
        self.notes        = notes
        self.last_updated = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<CanonicalEvent %r>' % (self.id)


class CanonicalEventLink(Base):
    __tablename__ = 'canonical_event_link'
    id           = Column(Integer, primary_key=True)
    coder_id     = Column(Integer, ForeignKey('user.id'), nullable = False)
    canonical_id = Column(Integer, ForeignKey('canonical_event.id'), nullable = False)
    cec_id       = Column(Integer, ForeignKey('coder_event_creator.id'), nullable = False)
    timestamp    = Column(DateTime)

    UniqueConstraint('canonical_id', 'cec_id', name = 'unique1')

    def __init__(self, coder_id, canonical_id, cec_id):
        self.coder_id     = coder_id
        self.canonical_id = canonical_id
        self.cec_id       = cec_id
        self.timestamp    = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<CanonicalEventLink %r>' % (self.id)


class CanonicalEventRelationship(Base):
    __tablename__ = 'canonical_event_relationship'
    id                = Column(Integer, primary_key=True)
    coder_id          = Column(Integer, ForeignKey('user.id'))
    canonical_id1     = Column(Integer, ForeignKey('canonical_event.id'))
    canonical_id2     = Column(Integer, ForeignKey('canonical_event.id'))
    relationship_type = Column(Text)
    timestamp         = Column(DateTime)

    UniqueConstraint('canonical_id1', 'canonical_id2', 'relationship_type', name = 'unique1')

    def __init__(self, coder_id, canonical_id1, canonical_id2, relationship_type):
        self.coder_id          = coder_id
        self.canonical_id1     = canonical_id1
        self.canonical_id2     = canonical_id2
        self.relationship_type = relationship_type
        self.timestamp         = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<CanonicalEventRelationship %r -> %r (%r)>' % \
            (self.canonical_id1, self.canonical_id2, self.relationship_type)


class EventFlag(Base):
    __tablename__ = 'event_flag'
    id        = Column(Integer, primary_key=True)
    coder_id  = Column(Integer, ForeignKey('user.id'))
    event_id  = Column(Integer, ForeignKey('event.id'))
    flag      = Column(Text)
    timestamp = Column(DateTime)

    UniqueConstraint('event_id', name = 'unique1')

    def __init__(self, coder_id, event_id, flag):
        self.coder_id  = coder_id
        self.event_id  = event_id
        self.flag      = flag
        self.timestamp = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<EventFlag %r (%r)>' % (self.event_id, self.flag)


class EventMetadata(Base):
    __tablename__ = 'event_metadata'
    id           = Column(Integer, primary_key=True)
    coder_id     = Column(Integer, ForeignKey('user.id'))
    event_id     = Column(Integer, ForeignKey('event.id'))
    article_id   = Column(Integer, ForeignKey('article_metadata.id'))
    article_desc = Column(UnicodeText, nullable = True)
    desc         = Column(UnicodeText, nullable = True)
    location     = Column(Text, nullable = True)
    start_date   = Column(Date, nullable = True)
    publication  = Column(Text)
    pub_date     = Column(Date)
    title        = Column(Text)
    form         = Column(Text)
    issue        = Column(Text)
    racial_issue = Column(Text)

    UniqueConstraint('event_id', name = 'unique1')

    def __init__(self, coder_id, event_id, article_id, article_desc, desc, 
        location, start_date, publication, pub_date, title, 
        form, issue, racial_issue):
        self.coder_id     = coder_id
        self.event_id     = event_id
        self.article_id   = article_id
        self.article_desc = article_desc
        self.desc         = desc
        self.location     = location
        self.start_date   = start_date
        self.publication  = publication
        self.pub_date     = pub_date
        self.title        = title
        self.form         = form
        self.issue        = issue
        self.racial_issue = racial_issue
        
    def __repr__(self):
        return '<EventMetadata %r>' % (self.event_id)


class RecentCanonicalEvent(Base):
    __tablename__ = 'recent_canonical_event'
    id            = Column(Integer, primary_key=True)
    coder_id      = Column(Integer, ForeignKey('user.id'))
    canonical_id  = Column(Integer, ForeignKey('canonical_event.id'))
    last_accessed = Column(DateTime)

    UniqueConstraint('coder_id', 'canonical_id', name = 'unique1')

    def __init__(self, coder_id, canonical_id):
        self.coder_id      = coder_id
        self.canonical_id  = canonical_id
        self.last_accessed = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<RecentCanonicalEvent %r (%r)>' % (self.canonical_id, self.last_accessed)


class RecentEvent(Base):
    __tablename__ = 'recent_event'
    id            = Column(Integer, primary_key=True)
    coder_id      = Column(Integer, ForeignKey('user.id'))
    event_id      = Column(Integer, ForeignKey('event.id'))
    last_accessed = Column(DateTime)

    UniqueConstraint('coder_id', 'event_id', name = 'unique1')

    def __init__(self, coder_id, event_id):
        self.coder_id      = coder_id
        self.event_id      = event_id
        self.last_accessed = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<RecentEvent %r (%r)>' % (self.event_id, self.last_accessed)


class RecentSearch(Base):
    __tablename__ = 'recent_search'
    id            = Column(Integer, primary_key=True)
    coder_id      = Column(Integer, ForeignKey('user.id'))
    field         = Column(Text)
    comparison    = Column(Text)
    value         = Column(Text)
    last_accessed = Column(DateTime)

    UniqueConstraint('coder_id', 'field', 'comparison', 'value', name = 'unique1')

    def __init__(self, coder_id, field, comparison, value):
        self.coder_id      = coder_id
        self.field         = field
        self.comparison    = comparison
        self.value         = value
        self.last_accessed = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<RecentSearch %r-%r-%r (%r)>' % \
            (self.field, self.comparison, self.value, self.last_accessed)


class CodeFirstPass(Base):
    __tablename__ = 'coder_first_pass'
    id         = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('article_metadata.id'), nullable = False)
    variable   = Column(String(100), nullable = False)
    value      = Column(String(2000), nullable = False)
    text       = Column(Unicode(2000))
    coder_id   = Column(Integer, ForeignKey('user.id'), nullable = False)
    timestamp  = Column(DateTime)

    def __init__(self, article_id, variable, value, coder_id, text = None):
        self.article_id = article_id
        self.variable   = variable
        self.value      = value
        self.text       = text
        self.coder_id   = coder_id
        self.timestamp  = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<CodeFirstPass %r>' % (self.id)


class CodeSecondPass(Base):
    __tablename__ = 'coder_second_pass'
    id         = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('article_metadata.id'), nullable = False)
    event_id   = Column(Integer, ForeignKey('event.id'), nullable = False)
    variable   = Column(String(100), nullable = False)
    value      = Column(String(2000), nullable = False)
    coder_id   = Column(Integer, ForeignKey('user.id'))
    timestamp  = Column(DateTime)

    def __init__(self, article_id, event_id, variable, value, coder_id):
        self.article_id = article_id
        self.event_id   = event_id
        self.variable   = variable
        self.value      = value
        self.coder_id   = coder_id
        self.timestamp  = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<CodeSecondPass %r>' % (self.id)


class CodeEventCreator(Base):
    __tablename__ = 'coder_event_creator'
    id         = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('article_metadata.id'), nullable = False)
    event_id   = Column(Integer, ForeignKey('event.id'), nullable = False)
    variable   = Column(String(100), nullable = False)
    value      = Column(Text, nullable = False)
    text       = Column(UnicodeText)
    coder_id   = Column(Integer, ForeignKey('user.id'))
    timestamp  = Column(DateTime)

    def __init__(self, article_id, event_id, variable, value, coder_id, text = None):
        self.article_id = article_id
        self.event_id   = event_id
        self.variable   = variable
        self.value      = value
        self.text       = text
        self.coder_id   = coder_id
        self.timestamp  = dt.datetime.now(tz = central).replace(tzinfo = None)

    def __repr__(self):
        return '<CodeEventCreator %r>' % (self.id)


class Event(Base):
    __tablename__ = 'event'
    id         = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('article_metadata.id'), nullable = False)

    def __init__(self, article_id):
        self.article_id = article_id

    seconds = relationship("CodeSecondPass", backref = backref("event", order_by = id))

    def __repr__(self):
        return '<Event %r>' % (self.id)


class ArticleQueue(Base):
    __tablename__ = 'article_queue'
    id         = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('article_metadata.id'), nullable = False)
    coder_id   = Column(Integer, ForeignKey('user.id'), nullable = False)
    coded_dt   = Column(DateTime)

    UniqueConstraint('article_id', 'coder_id', name = 'unique1')

    def __init__(self, article_id, coder_id):
        self.article_id = article_id
        self.coder_id   = coder_id

    def __repr__(self):
        return '<ArticleQueue %r>' % (self.article_id)


class SecondPassQueue(Base):
    __tablename__ = 'second_pass_queue'
    id         = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('article_metadata.id'), nullable = False)
    coder_id   = Column(Integer, ForeignKey('user.id'), nullable = False)
    coded_dt   = Column(DateTime)

    UniqueConstraint('article_id', 'coder_id', name = 'unique1')

    def __init__(self, article_id, coder_id):
        self.article_id = article_id
        self.coder_id   = coder_id

    def __repr__(self):
        return '<SecondPassQueue %r>' % (self.article_id)


class EventCreatorQueue(Base):
    __tablename__ = 'event_creator_queue'
    id         = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('article_metadata.id'), nullable = False)
    coder_id   = Column(Integer, ForeignKey('user.id'), nullable = False)
    coded_dt   = Column(DateTime)

    UniqueConstraint('article_id', 'coder_id', name = 'unique1')

    def __init__(self, article_id, coder_id):
        self.article_id = article_id
        self.coder_id   = coder_id

    def __repr__(self):
        return '<EventCreatorQueue %r>' % (self.article_id)


class ArticleMetadata(Base):
    __tablename__ = 'article_metadata'
    id                  = Column(Integer, primary_key=True)
    title               = Column(String(1024))
    db_name             = Column(String(64))
    db_id               = Column(String(255))
    filename            = Column(String(255), nullable = False)
    pub_date            = Column(Date)
    publication         = Column(String(511))
    source_description  = Column(String(511))
    ## FIXME: Collation arg may will break anything but MySQL 5.7
    text                = Column(UnicodeText(4194300,
                                 collation='utf8mb4_general_ci'))

    firsts  = relationship("CodeFirstPass",  backref = backref("article_metadata", order_by = id))
    seconds = relationship("CodeSecondPass", backref = backref("article_metadata", order_by = id))
    queue   = relationship("ArticleQueue",   backref = backref("article_metadata", order_by = id))

    def __init__(self,
                 filename,
                 db_name = None,
                 db_id = None,
                 title = None,
                 pub_date = None,
                 publication = None,
                 source_description = None,
                 text = None):
        self.filename           = filename
        self.db_name            = db_name
        self.db_id              = db_id
        self.title              = title
        self.pub_date           = pub_date
        self.publication        = publication
        self.source_description = source_description
        self.text               = text

    def __repr__(self):
        return '<ArticleMetadata %r (%r)>' % (self.title, self.id)


## All these are manually added
class User(Base, UserMixin):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    username  = Column(String(64), nullable = False)
    password  = Column(String(64), nullable = False)
    authlevel = Column(Integer, nullable = False)

    firsts  = relationship("CodeFirstPass",  backref = backref("user", order_by = id))
    seconds = relationship("CodeSecondPass", backref = backref("user", order_by = id))
    queue   = relationship("ArticleQueue",   backref = backref("user", order_by = id))

    def __init__(self, username, password, authlevel):
        self.username  = username
        self.password  = password
        self.authlevel = authlevel

    # def get_id(self):
    #     try:
    #         return unicode(self.id)  # python 2
    #     except NameError:
    #         return str(self.id)  # python 3

    def __repr__(self):
        return '<Coder %r>' % (self.username)


class FormTemplate(Base):
    __tablename__ = 'form_template'
    id = Column(Integer, primary_key = True, autoincrement=True)
    template_name = Column(String(10000), nullable = False)
    template_content = Column(Text, nullable = False)
    modified_time = Column(DateTime, onupdate=dt.datetime.now)

    def __init__(self, template_name, template_content):
        self.template_name = template_name
        self.template_content = template_content

    def __repr__(self):
        return '<FormTemplaste %r>\nname: %s' % (self.id, self.template_name)
