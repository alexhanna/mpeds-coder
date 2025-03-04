# -*- coding: utf-8 -*-
"""
    MPEDS Annotation Interface
    ~~~~~~

    Alex Hanna
    @alexhanna
    alex.hanna@gmail.com
"""

## base
import json
import math
import os
import re
import string
import sys
import urllib
import datetime as dt
from random import choice
import yaml
from collections import OrderedDict

import urllib.request

## pandas
import pandas as pd
import numpy as np

## lxml, time
from lxml import etree
from pytz import timezone

## flask
from flask import Flask, request, session, g, redirect, url_for, abort, make_response,\
    render_template, send_file, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, current_user, login_required

## jinja
import jinja2

## article assignment library
from .assign_lib import *

## db
from sqlalchemy import func, desc, distinct, and_, or_

## app-specific
from .database import db_session

from .models import ArticleMetadata, ArticleQueue, CanonicalEvent, CanonicalEventLink, CanonicalEventRelationship, \
    CoderArticleAnnotation, CodeFirstPass, CodeSecondPass, CodeEventCreator, \
    Event, EventCreatorQueue, EventFlag, EventMetadata, \
    RecentEvent, RecentCanonicalEvent, SecondPassQueue, User

##### Enable OrderedDict with PyYAML
##### Copy-pasta from https://stackoverflow.com/a/21912744 on 2019-12-12
def ordered_load(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
    class OrderedLoader(Loader):
        pass
    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(stream, OrderedLoader)

# create our application
app = Flask(__name__)
app.config.from_pyfile('config.py')

# customize template path
# copy-pasta from https://stackoverflow.com/questions/13598363/how-to-dynamically-select-template-directory-to-be-used-in-flask
if 'ADDITIONAL_TEMPLATE_DIR' in app.config and app.config.get('ADDITIONAL_TEMPLATE_DIR'):
    template_loader = jinja2.ChoiceLoader([
        jinja2.FileSystemLoader([app.config['ADDITIONAL_TEMPLATE_DIR']]),
        app.jinja_loader])
    app.jinja_loader = template_loader


## login stuff
lm  = LoginManager()
lm.init_app(app)
lm.login_view = 'login'

## retrieve central time
central = timezone('US/Central')

## open-ended vars
v2 = [
    ('loc',    'Location'),
    ('time',   'Timing and Duration'),
    ('size',   'Size'),
    ('orgs',   'Organizations')
]

## informational vars
v3 = [
    ('actor',  'Protest actors'),
    ('police', 'Police/protester interactions'),
    ('counter','Counter protests'),
    ('viol',   'Violence')
]

event_creator_vars = []

## if there's the yaml text selects
if os.path.isfile(app.config['WD'] + '/text-selects.yaml'):
    ecs = yaml.load(open(app.config['WD'] + '/text-selects.yaml', 'r'), 
                    Loader = yaml.Loader)
    event_creator_vars = [(x, ecs[x]) for x in sorted(ecs.keys())]
elif os.path.isfile(app.config['WD'] + '/text-selects.csv'):
    for var in open(app.config['WD'] + '/text-selects.csv', 'r').read().split('\n'):
        var = var.strip()
        if var:
            key  = '-'.join(re.split('[ /]', var.lower()))
            key += '-text'
            event_creator_vars.append( (key, var) )

## load adj grid order
adj_grid_order = []
if os.path.isfile(app.config['WD'] + '/adj-grid-order.yaml'):
    adj_load = yaml.load(open(app.config['WD'] + '/adj-grid-order.yaml', 'r'), 
        Loader = yaml.Loader)

    for x in adj_load:
        k,v = list(x.items())[0]
        adj_grid_order.append( (k,v) )

## load preset variables
preset_vars = yaml.load(open(app.config['WD'] + '/presets.yaml', 'r'), 
                        Loader = yaml.Loader)
v1 = [(x, str.title(x).replace('-', ' ')) for x in sorted(preset_vars.keys())]

## load ordered present variables
preset2_vars = ordered_load(open(app.config['WD'] + '/presets2.yaml', 'r'))
v4 = [(x, str.title(x).replace('-', ' ')) for x in preset2_vars.keys()]

## multiple variable keys
multi_vars_keys = v1[:] 
multi_vars_keys.extend(event_creator_vars[:])
multi_vars_keys.extend(v4[:])
multi_vars_keys = [x[0] for x in multi_vars_keys]

## pass one variables
vars = v1[:]
vars.extend(v2[:])
vars.extend(v3[:])
vars.extend(v4[:])

## single value variables for first-pass coding
sv = ['comments', 'protest', 'multi', 'nous', 'ignore']

## yaml for yes/no variables
yes_no_vars = yaml.load(open(app.config['WD'] + '/yes-no.yaml', 'r'))

## yaml for states/provinces/territories
if app.config['USE_STATES_AND_TERR']:
    state_and_territory_vals = ordered_load(open(app.config['WD'] + '/states.yaml', 'r'))
    #state_and_territory_vals = OrderedDict([('b', 2), ('a', 1), ('c', 3)])
else:
    state_and_territory_vals = dict()

## mark the single-valued items
event_creator_single_value = app.config['SINGLE_VALUE_VARS']
event_creator_single_value.extend([[x[0] for x in v] for k, v in yes_no_vars.iteritems()])

## metadata for Solr
meta_solr = ['PUBLICATION', 'SECTION', 'BYLINE', 'DATELINE', 'DATE', 'INTERNAL_ID']

#####
##### Helper functions
#####

##### load text from Solr database
def loadSolr(solr_id):
    solr_id    = urllib.quote(solr_id)
    url        = '%s/select?q=id:"%s"&wt=json' % (app.config['SOLR_ADDR'], solr_id)
    not_found  = (0, [], [])
    no_connect = (-1, [], [])

    try:
        if (sys.version_info < (3, 0)):
            ## Python 2
            req  = urllib2.Request(url)
            res  = urllib2.urlopen(req)
        else:
            ## Python 3
            res = urllib.request.urlopen(url)
    except:
        return no_connect
    res = json.loads(res.read())
    if res['responseHeader']['status'] != 0:
        return not_found

    if len(res['response']['docs']) != 1:
        return not_found

    doc = res['response']['docs'][0]

    ## sometimes no text is available with AGW
    if 'TEXT' not in doc:
        return (-2, [], [])

    paras = doc['TEXT'].split('<br/>')
    meta  = []
    for k in meta_solr:
        if k in doc:
            if k == 'DATE':
                meta.append(doc[k][0].split('T')[0])
            else:
                meta.append(doc[k])

    if 'TITLE' in doc:
        title = doc['TITLE']
    else:
        title = paras[0]
        del paras[0]

    return title, meta, paras

## prep any article for display
def prepText(article):
    fn                 = article.filename
    db_id              = article.db_id
    atitle             = article.title
    pub_date           = article.pub_date
    publication        = article.publication
    fulltext           = article.text

    metawords = ['DATE', 'PUBLICATION', 'LANGUAGE', 'DATELINE', 'SECTION',
    'EDITION', 'LENGTH', 'DATE', 'SEARCH_ID', 'Published', 'By', 'AP', 'UPI']

    text  = ''
    html  = ''
    title = ''
    meta  = []
    paras = []
    path  = app.config['DOC_ROOT'] + fn

    filename = str('INTERNAL_ID: %s' % fn.encode('utf8'))

    if app.config['STORE_ARTICLES_INTERNALLY'] == True:
        title = atitle
        meta = [publication, pub_date, db_id]
        paras = fulltext.split('<br/>')
    elif app.config['SOLR'] == True:
        title, meta, paras = loadSolr(db_id)
        if title == 0:
            title = "Cannot find article in Solr."
        elif title == -1:
            title = "Cannot connect to Solr."
        elif title == -2:
            title = "No text. Skip article."
    elif re.match(r"^.+txt$", fn):
        i     = 0
        title = ''
        pLine = ''

        f = open(path, 'r')

        for line in f:
            line  = line.strip()
            words = line.split()

            ## remove colon from first word in the line
            if len(words) > 0:
                words[0] = words[0].replace(":", '')

            if False:
                pass
            elif line == '':
                pass
            elif i == 0:
                ## first line is title
                if words[0] == 'TITLE':
                    line = " ".join(words[1:])

                title = line
            elif pLine != '' and words[0] in metawords:
                meta.append(line)
            else:
                ## add to html
                paras.append(line)

            i += 1
            pLine = line

        ## append filename info
        meta.append(filename)
    elif re.match(r"^.+xml$", fn):
        ## this format only works for LDC XML files
        tree     = etree.parse(open(path, "r"))
        headline = tree.xpath("/nitf/body[1]/body.head/hedline/hl1")
        paras    = tree.xpath("/nitf/body/body.content/block[@class='full_text']/p")
        lead     = tree.xpath("/nitf/body/body.content/block[@class='lead_paragraph']/p")
        byline   = tree.xpath("/nitf/body/body.head/byline[@class='print_byline']")
        dateline = tree.xpath("/nitf/body/body.head/dateline")

        if len(byline):
            meta.append(byline[0].text)

        if len(dateline):
            meta.append(dateline[0].text)

        meta.append(filename)

        title = headline[0].text
        paras = [x.text for x in paras]

    ## get rid of lead if it says the same thing
    if len(paras) > 0:
        p0 = paras[0]
        p0 = p0.replace("LEAD: ", "")
        if len(paras) > 1:
            if p0 == paras[1]:
                del paras[0]

    ## remove HTML from every paragraph
    paras = [re.sub(r'<[^>]*>', '', x) for x in paras]
             
    ## paste together paragraphs, give them an ID
    all_paras = ""
    for i, text in enumerate(paras):
        all_paras += "<p id='%d'>%s</p>\n" % (i, text)
    all_paras = all_paras.strip()

    html  = "<h4>%s</h4>\n" % title
    html += "<p class='meta' id='meta'>%s</p>\n" % " | ".join(map(lambda x: "%s" % x, meta)).strip()
    html += "<div class='bodytext' id='bodytext'>\n%s\n</div>" % all_paras

    ## plain-text
    text = "\n".join(paras)

    text = text.encode("utf-8")
    html = html.encode("utf-8")

    return text, html

def validate( x ):
    """ replace newlines, returns, and tabs with blank space """
    if x:
        if type(x) == str.unicode:
            x = string.replace(x, "\n", " ")
            x = string.replace(x, "\r", " ")
            x = string.replace(x, "\t", " ")
            return x.encode('utf-8')
        else:
            return str(x)
    else:
        return "0"

def convertIDToPublication(db_id, db_name):
    """ Takes a Solr ID and spits out the publication"""

    if 'AGW' in db_id:
        ## AGW-XXX-ENG_YYYYMMDD.NNNN
        r = db_id.split("_")[1]
    elif 'NYT' in db_id:
        r = 'NYT'
    else:
        r = db_id.split("_")[0]

        ## replace - with space
        r = r.replace('-', ' ')

        ## add (87-95) to WaPo and USATODAY
        if 'LN' in db_name:
            r += " (87-95)"

    return r

## truncating text for summary
@app.template_filter('summarizeText')
def summarizeText(s):
    if len(s) > 15:
        n = s[0:8] + "..." + s[-5:]
        return n
    return s


@app.template_filter('datetime')
def format_datetime(value):
    if value:
        return dt.datetime.strftime(value, "%Y-%m-%d %H:%M:%S")
    return ''


@app.template_filter('nonestr')
def nonestr(s):
    if s is not None:
        return s
    return ''


## java string hashcode
## copy-pasta from http://garage.pimentech.net/libcommonPython_src_python_libcommon_javastringhashcode/
## make it a Jinja2 filter for template ease
@app.template_filter('hashcode')
def hashcode(s):
    h = 0
    for c in s:
        h = (31 * h + ord(c)) & 0xFFFFFFFF
    a = ((h + 0x80000000) & 0xFFFFFFFF) - 0x80000000

    return int(math.fabs(a))

#####
##### App setup
#####

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

### auth stuff
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template("login.html")

    username = request.form['username']
    password = request.form['password']
    reg_user = User.query.filter_by(username=username, password=password).first()
    if reg_user is None:
        flash("Username or password is invalid. Please try again.", "error")
        return redirect(url_for('login'))

    login_user(reg_user)
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@lm.user_loader
def load_user(id):
    return User.query.get(int(id))

## views
@app.route('/')
@app.route('/index')
@login_required
def index():
    return render_template("index.html")

#####
##### Coding pages
#####

@app.route('/code1')
@login_required
def code1Next():
    now     = dt.datetime.now(tz = central).replace(tzinfo = None)
    article = None

    while article == None:
        ## get next article in this user's queue
        next    = db_session.query(ArticleQueue).filter_by(coder_id = current_user.id, coded_dt = None).first()

        ## out of articles, return null page
        if next is None:
            return render_template("null.html")

        article = db_session.query(ArticleMetadata).filter_by(id = next.article_id).first()

        ## this is a weird error and shouldn't happen but here we are.
        if article is None:
            next.coded_dt = now
            db_session.add(next)
            db_session.commit()

    return redirect(url_for('code1', aid = next.article_id))


@app.route('/code1/<aid>')
@login_required
def code1(aid):
    article    = db_session.query(ArticleMetadata).filter_by(id = aid).first()
    text, html = prepText(article)

    aq = db_session.query(ArticleQueue).filter_by(coder_id = current_user.id, article_id = aid).first()

    return render_template("code1.html", vars = vars, aid = aid, text = html.decode('utf-8'))


@app.route('/code2')
@login_required
def code2Next():
    if current_user.authlevel < 2:
        return redirect(url_for('index'))

    nextArticle = db_session.query(SecondPassQueue).filter_by(coder_id = current_user.id, coded_dt = None).first()

    if nextArticle:
        return redirect(url_for('code2', aid = nextArticle.article_id))
    else:
        return render_template("null.html")


@app.route('/code2/<aid>')
@login_required
def code2(aid):
    if current_user.authlevel < 2:
        return redirect(url_for('index'))

    aid       = int(aid)
    cfp_order = ['protest', 'multi', 'nous']
    cfp_dict  = {cfp_name: {} for cfp_name in cfp_order}
    cfp_ex    = ['load', 'ignore']
    sv_order  = ['yes', 'no', 'maybe', 'ignore']
    comments  = []
    opts      = {}
    curr      = {}

    ## initialize the dictionary
    for v in vars:
        cfp_dict[v[0]] = 0

    ## gather coders which have coded this article
    ## and get single-valued items
    cfps           = db_session.query(CodeFirstPass).filter(CodeFirstPass.article_id == aid).all()
    coders_protest = [(x[1].username, x[0].value) for x in db_session.query(CodeFirstPass, User).join(User).\
        filter(CodeFirstPass.article_id == aid, CodeFirstPass.variable == 'protest').all()]
    yes_coders     = db_session.query(CodeFirstPass).\
        filter(CodeFirstPass.article_id == aid, CodeFirstPass.variable == 'protest', CodeFirstPass.value.in_(['yes', 'maybe'])).count()

    ## load the single-value variables
    for cfp in cfps:
        if cfp.variable in cfp_ex:
            continue
        elif cfp.variable == 'comments':
            comments.append(cfp.value)
        elif cfp.variable == 'ignore':
            ## assign ignore to protest
            if 'ignore' not in cfp_dict['protest']:
                cfp_dict['protest']['ignore'] = 0

            cfp_dict['protest']['ignore'] += 1
        elif cfp.variable in cfp_order:
            ## if in the dichotomous variables, sum values
            if cfp.value not in cfp_dict[cfp.variable]:
                cfp_dict[cfp.variable][cfp.value] = 0

            cfp_dict[cfp.variable][cfp.value] += 1
        else:
            ## else, just mark existence
            cfp_dict[cfp.variable] += 1

    article    = db_session.query(ArticleMetadata).filter_by(id = aid).first()
    text, html = prepText(article)

    return render_template(
        "code2.html",
        vars       = vars,
        aid        = aid,
        cfp_dict   = cfp_dict,
        cfp_order  = cfp_order,
        sv_order   = sv_order,
        comments   = comments,
        opts       = opts,
        curr       = curr,
        coders_p   = coders_protest,
        num_coders = len(coders_protest),
        yes_coders = float(yes_coders),
        text       = html.decode('utf-8'))


@app.route('/event_creator')
@login_required
def ecNext():
    nextArticle = db_session.query(EventCreatorQueue).filter_by(coder_id = current_user.id, coded_dt = None).first()

    if nextArticle:
        return redirect(url_for('eventCreator', aid = nextArticle.article_id))
    else:
        return render_template("null.html")


@app.route('/event_creator/<aid>')
@login_required
def eventCreator(aid):
    aid        = int(aid)
    article    = db_session.query(ArticleMetadata).filter_by(id = aid).first()
    text, html = prepText(article)

    return render_template("event-creator.html", aid = aid, text = html.decode('utf-8'))

#####
##### Adjudication
#####

@app.route('/adj', methods = ['GET'])
@login_required
def adj():
    """Initial rendering for adjudication page."""
    if current_user.authlevel < 2: 
        return redirect(url_for('index'))

    ## Filter fields for candidate search
    candidate_filter_fields = EventMetadata.__table__.columns.keys()
    candidate_filter_fields.remove('id')
    candidate_filter_fields.append('flag')

    ## Filter comparators for candidate search
    candidate_filter_compare = [
        ('eq', 'equals'), ('ne', 'not equal to'), 
        ('gt', 'is greater than'), ('ge', 'is greater than or equal to'),
        ('lt', 'is less than'), ('le', 'is less than or equal to'),
        ('contains', 'contains'), ('starts', 'starts with'), ('ends', 'ends with')
    ]
    
    ## Filter fields for canonical search
    canonical_filter_fields = ['key', 'start-date', 'location',
    'form', 'issue', 'racial-issue',
    'event_id', 'coder_id', 'description', 'notes']
    canonical_filter_compare = candidate_filter_compare[:]

    canonical_sort_fields = ['key', 'coder_id']

    return render_template("adj.html", 
        search_events  = [],
        candidate_filter_fields  = candidate_filter_fields,
        candidate_filter_compare = candidate_filter_compare,
        canonical_filter_fields  = canonical_filter_fields, 
        canonical_filter_compare = canonical_filter_compare,
        canonical_sort_fields = canonical_sort_fields,
        cand_events    = {},
        adj_grid_order = adj_grid_order,
        links          = [],
        flags          = [],
        recent_events  = [],
        recent_canonical_events = [],
        canonical_event = None)


@app.route('/load_adj_grid', methods = ['GET'])
@login_required
def load_adj_grid():
    """Loads the grid for the expanded event view."""
    ce_ids = request.args.get('cand_events')
    if ce_ids == 'null':
        ce_ids = None

    canonical_event_key = request.args.get('canonical_event_key')
    if canonical_event_key == 'null':
        canonical_event_key = None

    cand_event_ids = [int(x) for x in ce_ids.split(',')] if ce_ids else []

    ## store recent events
    _store_recent_events(cand_event_ids, canonical_event_key)

    ## do loading for the grid    
    cand_events = _load_candidate_events(cand_event_ids)
    canonical_event = _load_canonical_event(key = canonical_event_key)
    links = _load_links(canonical_event_key)
    event_flags = _load_event_flags(cand_event_ids)

    return render_template('adj-grid.html',
        canonical_event = canonical_event,
        cand_events = cand_events,
        links = links,
        flags = event_flags, 
        adj_grid_order = adj_grid_order)


@app.route('/load_recent_candidate_events', methods = ['POST'])
@login_required
def load_recent_candidate_events():
    """ Load and render most recent candidate events. """
    events = [x[0] for x in db_session.query(EventMetadata, RecentEvent)\
        .join(EventMetadata, EventMetadata.event_id == RecentEvent.event_id)\
        .filter(RecentEvent.coder_id == current_user.id)\
        .order_by(desc(RecentEvent.last_accessed)).limit(5).all()]

    return render_template('adj-search-block.html', events = events, flags = [])


@app.route('/load_recent_canonical_events', methods = ['POST'])
@login_required
def load_recent_canonical_events():
    """ Load and render most recent canonical events. """
    events = db_session.query(CanonicalEvent)\
        .join(RecentCanonicalEvent, CanonicalEvent.id == RecentCanonicalEvent.canonical_id)\
        .filter(RecentCanonicalEvent.coder_id == current_user.id)\
        .order_by(desc(RecentCanonicalEvent.last_accessed)).limit(5).all()

    users = {x.id: x.username for x in  db_session.query(User).all()}

    return render_template('adj-canonical-search-block.html', 
        events = events, 
        users = users,
        is_search = False)


@app.route('/load_canonical_hierarchy', methods = ['POST'])
@login_required
def load_canonical_hierarchy():
    """ Load and render canonical event hierarchy. """
    key = request.form['key']
    cid = _load_canonical_id_from_key(key)

    if not cid:
        return make_response("Invalid key.", 400)

    parents = db_session.query(CanonicalEvent, CanonicalEventRelationship)\
        .join(CanonicalEventRelationship, CanonicalEvent.id == CanonicalEventRelationship.canonical_id2)\
        .filter(CanonicalEventRelationship.canonical_id1 == cid)\
        .order_by(CanonicalEventRelationship.relationship_type, CanonicalEvent.key).all()

    children = db_session.query(CanonicalEvent, CanonicalEventRelationship)\
        .join(CanonicalEventRelationship, CanonicalEvent.id == CanonicalEventRelationship.canonical_id1)\
        .filter(CanonicalEventRelationship.canonical_id2 == cid)\
        .order_by(CanonicalEventRelationship.relationship_type, CanonicalEvent.key).all()            

    gcs = db_session.query(CanonicalEvent, CanonicalEventRelationship)\
        .join(CanonicalEventRelationship, CanonicalEvent.id == CanonicalEventRelationship.canonical_id1)\
        .filter(CanonicalEventRelationship.canonical_id2.in_([x[0].id for x in children])).all()

    ## index GCs by parents
    grandchildren = {}
    for ce, cer in gcs:
        if cer.canonical_id2 not in grandchildren:
            grandchildren[cer.canonical_id2] = [] 
        grandchildren[cer.canonical_id2].append((ce, cer))

    return render_template('adj-canonical-hierarchy.html',
        key = key,
        cid = cid,
        parents = parents, 
        children = children,
        grandchildren = grandchildren)

#####
## Search functions
#####

@app.route('/do_search/<search_mode>', methods = ['POST'])
@login_required
def do_search(search_mode):
    """Takes the URL params and searches events which meet the search criteria."""

    if search_mode not in ['candidate', 'canonical']:
        return make_response("Invalid search mode.", 400)

    search_str = request.form[search_mode + '_search_input']
    users = {x.id: x.username for x in db_session.query(User).all()}

    ## get multiple filters and sorting
    filters = []
    sorts = []

    ## cycle through all the filter and sort fields
    for i in range(4):
        filter_field = request.form[search_mode + '_filter_field_{}'.format(i)]
        filter_value = request.form[search_mode + '_filter_value_{}'.format(i)]
        filter_compare = request.form[search_mode + '_filter_compare_{}'.format(i)]

        if filter_field and filter_value and filter_compare:
            _model, filter_field, filter_value, _filter2 = _get_model_and_field(search_mode, filter_field, filter_value)

            ## Translate the filter compare to a SQLAlchemy expression.
            if filter_compare == 'eq':
                _filter = getattr(getattr(_model, filter_field), '__eq__')(filter_value)
            elif filter_compare == 'ne':
                _filter = getattr(getattr(_model, filter_field), '__ne__')(filter_value)
                ## in the case where we're excluding a flag, need to OR "flag IS NULL"
                if filter_field == 'flag' and search_mode == 'candidate':
                    _filter2 = getattr(getattr(_model, filter_field), '__eq__')(None)
                    _filter = or_(_filter, _filter2)
            elif filter_compare == 'lt':
                _filter = getattr(getattr(_model, filter_field), '__lt__')(filter_value)
            elif filter_compare == 'le':
                _filter = getattr(getattr(_model, filter_field), '__le__')(filter_value)
            elif filter_compare == 'gt':
                _filter = getattr(getattr(_model, filter_field), '__gt__')(filter_value)
            elif filter_compare == 'ge':
                _filter = getattr(getattr(_model, filter_field), '__ge__')(filter_value)
            elif filter_compare == 'contains':
                _filter = getattr(getattr(_model, filter_field), 'like')(u'%{}%'.format(filter_value))
            # TODO: Add when we convert this to Python 3
            # elif filter_compare == 'not_contains': 
            #     _filter = getattr(getattr(_model, filter_field), 'not_like')(u'%{}%'.format(filter_value))
            elif filter_compare == 'starts':
                _filter = getattr(getattr(_model, filter_field), 'like')(u'{}%'.format(filter_value))
            elif filter_compare == 'ends':
                _filter = getattr(getattr(_model, filter_field), 'like')(u'%{}'.format(filter_value))
            else:
                raise Exception('Invalid filter compare: {}'.format(filter_compare))

            ## AND the two filters together
            _filter = and_(_filter, _filter2)
            
            ## add to list of filters
            filters.append(_filter)

        sort_field = request.form[search_mode + '_sort_field_{}'.format(i)]
        sort_order = request.form[search_mode + '_sort_order_{}'.format(i)]

        if sort_field and sort_order:
            _model, sort_field, _, _ = _get_model_and_field(search_mode, sort_field, None)

            _sort = getattr(getattr(_model, sort_field), sort_order)()
            sorts.append(_sort)

    ## AND all the filters together
    filter_expr = and_(*filters)

    search_expr = None
    if search_str:
        ## Build the search expression. For now, it can only do an AND or OR search.
        operator = and_
        if ' AND ' in search_str:
            search_terms = map(lambda x: x.strip(), search_str.split(' AND '))
            operator = and_
        elif ' OR ' in search_str:
            search_terms = map(lambda x: x.strip(), search_str.split(' OR '))
            operator = or_
        else:
            search_terms = [search_str.strip()]

        ## only allow the free-form search in EventMetadata and CanonicalEvent fields
        _model = EventMetadata if search_mode == 'candidate' else CanonicalEvent

        ## get searchable metadata
        search_fields = _model.__table__.columns.keys()
        search_fields.remove('id')

        ## Build the search by creating an expression for each search term and search field.
        search_expr = []
        for term in search_terms:
            term_expr = []
            for field in search_fields:
                term_expr.append(getattr(getattr(_model, field), 'like')(u'%{}%'.format(term)))
            search_expr.append(or_(*term_expr))
        search_expr = operator(*search_expr) 

    ## Combine filters.
    a_filter_expr = None
    if search_mode == 'candidate':
        ## Filter out null start dates to account for disqualifying information.
        date_filter = EventMetadata.start_date != None
        if filter_expr is not None and search_expr is not None:
            a_filter_expr = and_(filter_expr, search_expr, date_filter)
        elif filter_expr is not None:
            a_filter_expr = and_(filter_expr, date_filter)
        elif search_expr is not None:
            a_filter_expr = and_(search_expr, date_filter)
        else:
            return make_response("Please enter a search term or a filter.", 400)
    else:
        if len(filters) == 0 and search_expr is None:
            return make_response("Please enter a search term or a filter.", 400)

    ## Perform the search on a left join to get all the candidate events.
    search_events = []
    if search_mode == 'candidate':
        search_events = db_session.query(EventMetadata).\
            join(EventFlag, EventMetadata.event_id == EventFlag.event_id, isouter = True).\
            filter(a_filter_expr).\
            order_by(*sorts).all()

        if len(search_events) > 1000:
            return make_response("Too many results. Please refine your search.", 400)

        ## get all flags for these events
        flags = _load_event_flags([x.event_id for x in search_events])

        response = make_response(
            render_template('adj-search-block.html', 
                events = search_events,
                flags = flags)
            )
    else:
        search_events_ids = None

        if search_str:
            filters.append(search_expr)

        ## need to do the intersect between different filterings
        for _filter in filters:
            rs = db_session.query(CanonicalEvent).\
                join(CanonicalEventLink, CanonicalEventLink.canonical_id == CanonicalEvent.id, isouter = True).\
                join(CodeEventCreator, CodeEventCreator.id == CanonicalEventLink.cec_id, isouter = True).\
                filter(_filter).all()

            rs = set([x.id for x in rs])
            print(search_expr, len(rs))

            ## if search_events is not null, then return the intersection of these two
            if search_events_ids is not None:
                search_events_ids = search_events_ids.intersection(rs)
            else:
                search_events_ids = rs

        ## lastly, get the full CanonicalEvents, sorted by key
        search_events = db_session.query(CanonicalEvent).\
            join(CanonicalEventLink, CanonicalEventLink.canonical_id == CanonicalEvent.id, isouter = True).\
            join(CodeEventCreator, CodeEventCreator.id == CanonicalEventLink.cec_id, isouter = True).\
            filter(CanonicalEvent.id.in_(search_events_ids)).\
            order_by(*sorts).all()
        
        if len(search_events) > 1000:
            return make_response("Too many results. Please refine your search.", 400)

        ## get the associated candidate events
        rs = db_session.query(CanonicalEvent, EventMetadata).\
            join(CanonicalEventLink, CanonicalEventLink.canonical_id == CanonicalEvent.id).\
            join(CodeEventCreator, CodeEventCreator.id == CanonicalEventLink.cec_id).\
            join(EventMetadata, EventMetadata.event_id == CodeEventCreator.event_id).\
            filter(
                CanonicalEvent.id.in_(search_events_ids), 
                CodeEventCreator.variable != 'link' 
            ).all()

        ## create a hashtable which maps canonical event keys to candidate events
        cand_events = {}
        for ce, em in rs:
            if ce.id not in cand_events:
                cand_events[ce.id] = {}
            cand_events[ce.id][em.event_id] = em

        response = make_response(
            render_template('adj-canonical-search-block.html', 
                events = search_events,
                cand_events = cand_events,
                users = users,
                is_search = True)
        )

    url_params = {k: v for k, v in request.form.iteritems()}

    ## make and return results. add in the number of results to update the button.
    response.headers['Search-Results'] = len(search_events)
    response.headers['Query'] = json.dumps(url_params)
    return response


@app.route('/search_canonical_autocomplete', methods=['POST'])
@login_required
def search_canonical_events():
    """Returns a list of canonical event keys based on search term for the autocomplete."""
    term = request.form['term']

    ## search for the canonical event in key 
    rs = db_session.query(CanonicalEvent).filter(CanonicalEvent.key.like('%{}%'.format(term))).all()

    ## return the list of canonical event keys
    return jsonify(result={"status": 200, "data": [x.key for x in rs]})


#####
## Grid functions
#####
@app.route('/add_canonical_link', methods = ['POST'])
@login_required
def add_canonical_link():
    """Adds a link from a article to a canonical event 
    when we don't want to add any data. """
    canonical_event_id = int(request.form['canonical_event_id'])
    article_id = int(request.form['article_id'])

    ## check if this link exists already
    res = db_session.query(CodeEventCreator, CanonicalEventLink)\
        .join(CanonicalEventLink, CodeEventCreator.id == CanonicalEventLink.cec_id)\
        .filter(
            CodeEventCreator.variable == 'link', 
            CodeEventCreator.article_id == article_id,
            CanonicalEventLink.canonical_id == canonical_event_id
        ).first()

    ## if the CEC and CEL are not null, 
    ## and CEL matches canonical event, then link this.
    if res and res[0] and res[1]:
        return make_response("Link already exists.", 400)

    ## for the link, create a new CEC and link it back to the canonical event
    ## we'll treat this as part of the dummy event
    cec = _check_or_add_dummy_value(article_id, 'link', 'yes')
    db_session.refresh(cec)

    ## add the link
    db_session.add(CanonicalEventLink(current_user.id, canonical_event_id, cec.id))
    db_session.commit()

    return make_response("Link added.", 200)    


@app.route('/add_canonical_record', methods = ['POST'])
@login_required
def add_canonical_record():
    """ Adds a candidate event datum to a canonical event. """
    canonical_event_id = int(request.form['canonical_event_id'])
    cec_id = int(request.form['cec_id'])

    ## grab CEC from the database
    record = db_session.query(CodeEventCreator)\
        .filter(CodeEventCreator.id == cec_id).first()

    ## if it's fake, toss it
    if not record:
        return make_response("No such CEC record.", 404)

    ## if it exists, toss it
    dupe_check = db_session.query(CanonicalEventLink)\
        .filter(
            CanonicalEventLink.cec_id == cec_id, 
            CanonicalEventLink.canonical_id == canonical_event_id)\
        .all()

    if dupe_check:
        return make_response("Record already exists.", 404)
        
    ## commit
    db_session.add(CanonicalEventLink(current_user.id, canonical_event_id, cec_id))
    db_session.commit()

    ## retrieve cel for timestamp
    cel = db_session.query(CanonicalEventLink)\
        .filter(
            CanonicalEventLink.coder_id == current_user.id,
            CanonicalEventLink.canonical_id == canonical_event_id,
            CanonicalEventLink.cec_id == cec_id
    ).first()

    value = record.value
    if record.text is not None:
        value = record.text
    return render_template('canonical-cell.html', 
        var = record.variable, 
        value = value,
        timestamp = cel.timestamp,
        cel_id = cel.id) 


@app.route('/add_canonical_relationship', methods = ['POST'])
@login_required
def add_canonical_relationship():
    key1 = request.form['key1']
    key2 = request.form['key2']
    rtype = request.form['type']

    if key1 == '' or key2 == '':
        return make_response("Please enter a key for both values.", 400)

    if key1 == key2:
        return make_response("Please enter two different keys.", 400)

    ## get ids
    id1 = _load_canonical_id_from_key(key1)
    id2 = _load_canonical_id_from_key(key2)

    if id1 is None or id2 is None:
        return make_response("One or more keys are invalid.", 400)

    ## check if this relationship exists already
    res = db_session.query(CanonicalEventRelationship)\
        .filter(
            CanonicalEventRelationship.canonical_id1 == id1,
            CanonicalEventRelationship.canonical_id2 == id2,
            CanonicalEventRelationship.relationship_type == rtype
        ).first()

    if res:
        return make_response("Relationship of this type already exists.", 400)

    ## commit
    db_session.add(CanonicalEventRelationship(current_user.id, id1, id2, rtype))
    db_session.commit()

    return make_response("Relationship added.", 200)


@app.route('/delete_canonical_relationship', methods = ['POST'])
@login_required
def delete_canonical_relationship():
    id1 = int(request.form['id1'])
    id2 = int(request.form['id2'])
    rtype = request.form['type']

    ## check if this relationship exists
    res = db_session.query(CanonicalEventRelationship)\
        .filter(
            CanonicalEventRelationship.canonical_id1 == id1,
            CanonicalEventRelationship.canonical_id2 == id2,
            CanonicalEventRelationship.relationship_type == rtype
        ).first()

    if not res:
        return make_response("Relationship does not exist.", 400)

    ## commit
    db_session.delete(res)
    db_session.commit()

    return make_response("Relationship deleted.", 200)


@app.route('/add_event_flag', methods = ['POST'])
@login_required
def add_event_flag():
    """Adds a flag to a candidate event."""
    event_id = int(request.form['event_id'])
    flag = request.form['flag']

    ## if we're adding a completed flag, remove all the other flags first
    if flag == 'completed':
        rs = db_session.query(EventFlag).filter(EventFlag.event_id == event_id).all()
        for r in rs:
            db_session.delete(r)
        db_session.commit()

    db_session.add(EventFlag(current_user.id, event_id, flag))
    db_session.commit()

    return make_response("Flag created.", 200)


@app.route('/delete_canonical', methods = ['POST'])
@login_required
def delete_canonical():
    """ Deletes the canonical event and related CEC links from the database."""
    key = request.form['key']

    ce = db_session.query(CanonicalEvent)\
        .filter(CanonicalEvent.key == key).first()
    cels = db_session.query(CanonicalEventLink)\
        .filter(CanonicalEventLink.canonical_id == ce.id).all()
    rces = db_session.query(RecentCanonicalEvent)\
        .filter(RecentCanonicalEvent.canonical_id == ce.id).all()
    relationships = db_session.query(CanonicalEventRelationship)\
        .filter(
            or_(CanonicalEventRelationship.canonical_id1 == ce.id, 
                CanonicalEventRelationship.canonical_id2 == ce.id)
        ).all()

    ## remove these first to avoid FK error
    for cel in cels:
        db_session.delete(cel)
    for rce in rces:
        db_session.delete(rce)
    for relationship in relationships:
        db_session.delete(relationship)
    db_session.commit()

    ## delete the actual event
    db_session.delete(ce)
    db_session.commit()
    
    return make_response("Canonical event deleted.", 200)


@app.route('/del_canonical_link', methods = ['POST'])
@login_required
def del_canonical_link():
    """Removes 'link' from a canonical event. 
       Remove it from the dummy event as well."""
    article_id = int(request.form['article_id'])

    ## get all the CECs for this article
    cecs = db_session.query(CodeEventCreator)\
        .filter(
            CodeEventCreator.article_id == article_id,
            CodeEventCreator.variable == 'link'
        ).all()

    for cec in cecs:
        ## get the CELs for this CEC
        cel = db_session.query(CanonicalEventLink).filter(CanonicalEventLink.cec_id == cec.id).first()
        if cel:
            db_session.delete(cel)

    ## commit these deletes first to avoid foreign key error
    db_session.commit()

    ## then delete CECs
    for cec in cecs:
        db_session.delete(cec)
    db_session.commit()

    return make_response("Link removed.", 200)


@app.route('/del_canonical_record', methods = ['POST'])
@login_required
def del_canonical_record():
    """ Removes the link between a candidate event piece of data and a canonical event. """
    cel_id = int(request.form['cel_id'])

    ## grab it from the database
    cel = db_session.query(CanonicalEventLink)\
        .filter(CanonicalEventLink.id == cel_id).first()

   ## if it's fake, toss it
    if not cel:
        return make_response("No such CEL record.", 404)
        
    ## delete and commit
    db_session.delete(cel)
    db_session.commit()
 
    return make_response("Delete successful.", 200)


@app.route('/del_event_flag', methods = ['POST'])
@login_required
def del_event_flag():
    """Deletes a flag to a candidate event."""
    event_id = int(request.form['event_id'])

    ## delete flag, regardless of the user who put it there.
    efs = db_session.query(EventFlag).filter(EventFlag.event_id == event_id).all()

    for ef in efs:
        db_session.delete(ef)
    db_session.commit()

    return make_response("Flag deleted.", 200)


@app.route('/download_canonical/<event_ids>', methods = ['GET'])
@login_required
def download_canonical(event_ids):
    """ Downloads canonical events based on IDs. Serves it as a CSV. """
    event_ids = [int(x) for x in event_ids.split(',')]
    all_data = []

    for canonical_id in event_ids:
        data = {}
        ce   = db_session.query(CanonicalEvent).filter(CanonicalEvent.id == canonical_id).first()
        cecs = db_session.query(CodeEventCreator).\
            join(CanonicalEventLink, CodeEventCreator.id == CanonicalEventLink.cec_id).\
            filter(CanonicalEventLink.canonical_id == ce.id).all()

        ## get all canonical metadata
        data['key'] = ce.key
        data['coder'] = db_session.query(User).filter(User.id == ce.coder_id).first().username
        data['description'] = ce.description
        data['notes'] = ce.notes

        ## load all the CEC data from the database
        for cec in cecs:
            if cec.variable not in data:
                data[cec.variable] = []
            data[cec.variable].append(cec.text if cec.text else cec.value)

        ## collapse lists
        for k in data.keys():
            if type(data[k]) == list:
                data[k] = ';'.join(data[k])
        
        all_data.append(data)

    path = '{}/exports/canonical-events_{}.csv'.\
        format(app.config['WD'],
        dt.datetime.now().strftime('%Y-%m-%d_%H%M%S'))

    ## let pandas do all the heavy lifting for CSV formatting
    df = pd.DataFrame(all_data)
    df = df.set_index('key')
    
    ## order of presenting
    df_order = ['coder', 'description', 'notes']

    ## add in columns which are not in the dataframe
    for k in [k[0] for k in adj_grid_order]:
        if k not in df.columns:
            df[k] = pd.Series()

        df_order.append(k)

    ## reorder the columns
    df = df[df_order]

    ## write to file
    df.to_csv(path, encoding = 'utf-8')

    return send_file(path, as_attachment = True)


@app.route('/modal_edit/<variable>/<mode>', methods = ['POST'])
@login_required
def modal_edit(variable, mode):
    """ Handler for modal display and form submission. """
    if variable == 'canonical':
        ce_id = request.form['canonical-id'] 
        key   = request.form['canonical-event-key']
        desc  = request.form['canonical-event-desc']
        notes = request.form['canonical-event-notes']
            
        if mode == 'add':
            if not key:
                return make_response("Please enter text for the key.", 400)

            if key:
                q = db_session.query(CanonicalEvent).filter(CanonicalEvent.key == key).all()
                if len(q) > 0: 
                    return make_response("Key already exists.", 400)                

            ce = CanonicalEvent(coder_id = current_user.id, key = key, description = desc, notes = notes)
        elif mode == 'edit':
            ## update key + notes upon edit
            ce = db_session.query(CanonicalEvent).filter(CanonicalEvent.id == ce_id).first()
            original_key = ce.key

            if key != original_key:
                q = db_session.query(CanonicalEvent).filter(CanonicalEvent.key == key).first()
                if q: 
                    return make_response("Key already exists. Pick another key to change to.", 400)

            ce.key = key
            ce.description = desc
            ce.notes = notes

        db_session.add(ce)
        db_session.commit()

        ## Return new event and put the new ID in the header.
        return make_response("Canonical event {}ed.".format(mode), 200)
    else:
        article_id = request.form['article-id']
        value = request.form['value']
        ce_id = request.form['canonical-id']

        if not article_id:
            return make_response("Please select an article ID.", 400)

        article_id = int(article_id)
        if mode == 'add':
            ## check to see if this has a dummy value
            ## if it does, link it. otherwise, this adds it
            cec = _check_or_add_dummy_value(article_id, variable, value)

            ## lastly, add the link to the canonical event
            cel = CanonicalEventLink(current_user.id, ce_id, cec.id)
            db_session.add(cel)
            db_session.commit()

            return make_response("{} added.".format(variable), 200)


@app.route('/modal_view', methods = ['POST'])
@login_required
def modal_view():
    """Returns the template for the modal, based on the variable."""
    article_ids = []
    variable = request.form['variable']
    edit = True if request.form.get('edit') == 'true' else False

    ## get the canonical event to get the ID later
    ce = None
    key = request.form.get('key')
    if key:
        ce = db_session.query(CanonicalEvent).\
            filter(CanonicalEvent.key == key).first()

    ## for non-canonical adds, get the article IDs associated with current candidate events
    if variable != 'canonical':
        candidate_events = request.form['candidate_event_ids'].split(',')
        article_ids = [x.article_id for x in db_session.query(Event).filter(Event.id.in_(candidate_events)).all()]
 
        ## get distinct values
        article_ids = sorted(list(set(article_ids)))

        return render_template('modal.html', 
            variable = variable, 
            ce = ce,
            article_ids = article_ids,
            preset_vars = preset_vars)
    else:
        return render_template('modal.html', variable = variable, ce = ce, edit = edit)
            

#####
# Adjudication helper functions
#####
@app.route('/_check_or_add_dummy')
@login_required
def _check_or_add_dummy_value(article_id, variable, value):
    """Check if selected article has any associated candidate event entries
        Just get the first, since we'll associate that with all dummy events."""
    cec = db_session.query(CodeEventCreator).\
        filter(
            CodeEventCreator.article_id == article_id,
            CodeEventCreator.coder_id == current_user.id
        ).first()

    ## if they do, get the event ID
    event_id = None
    if cec:
        event_id = cec.event_id
    else:
        ## otherwise, make a new event with this article ID
        cand_event = Event(article_id)
        db_session.add(cand_event)
        db_session.flush()

        ## refresh to get the event ID
        db_session.refresh(cand_event)
        event_id = cand_event.id

    ## if it doesn't exist. Add the value.
    cec = CodeEventCreator(article_id, event_id, variable, value, current_user.id)
    db_session.add(cec)
    db_session.flush()

    ## refresh to get the CEC ID
    db_session.refresh(cec)

    return cec


@app.route('/_get_model_and_field')
@login_required
def _get_model_and_field(search_mode, field, value):
    """ Return the correct model and field for filter and sort in searches. """
    users = {x.id: x.username for x in db_session.query(User).all()}
    rev_users = {v: k for k,v in users.iteritems()}

    _model = None
    _field = field
    _value = value
    _filter2 = True
    if search_mode == 'candidate':
        ## for candidate search, EventMetadata is the model for all the search fields, 
        ## except if we're searching for a flag
        _model = EventMetadata if field != 'flag' else EventFlag
    elif search_mode == 'canonical':
        ## for canonical search, CodeEventCreator is the model for everything but event_id,
        ## but the correct "field" is "variable" and we need to add an additional filter 
        if field in ['start-date', 'location', 'form', 'issue', 'racial-issue', 'event_id']:
            _model = CodeEventCreator
            if field != 'event_id':
                ## these need additional criteria to be ANDed into the main filter
                ## WHERE cec.variable = field (e.g. location, form)
                _filter2 = getattr(getattr(_model, 'variable'), '__eq__')(field)

                ## AND cec.value = value (e.g. user-defined value)
                _field = 'value'
        else:
            _model = CanonicalEvent
            if field == 'coder_id':
                if value is not None:
                    if value in rev_users:
                        _value = rev_users[value]
                    else:
                        raise Exception('User not found.')
    else:
        raise Exception('Invalid search mode: {}'.format(search_mode)) 

    return (_model, _field, _value, _filter2)

@app.route('/_load_candidate_events')
@login_required
def _load_candidate_events(cand_event_ids):
    """Helper function to load candidate events from the database.
    Returns a dict of candidate events, keyed by id."""
    cand_events = {x: {} for x in cand_event_ids}

    ## load in metadata
    for metadata in db_session.query(EventMetadata).\
        filter(EventMetadata.event_id.in_(cand_event_ids)).all():
        cand_events[metadata.event_id]['metadata'] = {}

        for field in app.config['ADJ_METADATA']:
            cand_events[metadata.event_id]['metadata'][field] = metadata.__getattribute__(field)

    for field in db_session.query(CodeEventCreator).\
        filter(CodeEventCreator.event_id.in_(cand_event_ids)).all():

        ## create a new list if it doesn't exist
        if not cand_events[field.event_id].get(field.variable):
            cand_events[field.event_id][field.variable] = []
        
        ## insert in record
        if field.text is not None:
            value = field.text
        else:
            value = field.value

        cand_events[field.event_id][field.variable].append((value, field.id, field.timestamp))
    
    return cand_events


@app.route('/_load_canonical_event')
@login_required
def _load_canonical_event(id = None, key = None):
    """Loads the canonical event and related CEC links from the database.
       To be displayed in the expanded event view grid."""
    if not id and not key:
        return None

    canonical_event = {}
    ces = None
    _filter = None
    if id:
        canonical_event['id'] = id
        _filter = CanonicalEvent.id == id
    else:
        canonical_event['key'] = key
        _filter = CanonicalEvent.key == key

    ce  = db_session.query(CanonicalEvent).filter(_filter).first()
    ces = db_session.query(CanonicalEvent, CanonicalEventLink, CodeEventCreator, User).\
        join(CanonicalEventLink, CanonicalEvent.id == CanonicalEventLink.canonical_id).\
        join(CodeEventCreator, CanonicalEventLink.cec_id == CodeEventCreator.id).\
        join(User, CodeEventCreator.coder_id == User.id).\
        filter(_filter).all()

    if not ce:
        return None

    ## load CE data
    canonical_event['id'] = ce.id
    canonical_event['key'] = ce.key
    canonical_event['description'] = ce.description
    canonical_event['notes'] = ce.notes

    for _, cel, cec, user in ces:
        ## create a new list if it doesn't exist
        if not canonical_event.get(cec.variable):
            canonical_event[cec.variable] = []

        ## insert in record
        value = None
        if cec.text is not None:
            value = cec.text
        else:
            value = cec.value

        ## if this is a dummy value, username starts with adj
        is_dummy = 1 if 'adj' in user.username else 0

        canonical_event[cec.variable].append((cel.id, value, cel.timestamp, cec.event_id, is_dummy))

    return canonical_event


@app.route('/_load_canonical_id_from_key')
@login_required
def _load_canonical_id_from_key(key):
    """Helper function to load the canonical event ID from the key."""
    cid = db_session.query(CanonicalEvent.id).\
        filter(CanonicalEvent.key == key).first()

    if not cid:
        return None
    return cid[0]


@app.route('/_load_event_flags')
@login_required
def _load_event_flags(events):
    """Loads the event flags for candidate events."""
    efs = db_session.query(EventFlag).\
        filter(
            EventFlag.event_id.in_(events)
        ).all()
    return {x.event_id: x.flag for x in efs}


@app.route('/_load_links')
@login_required
def _load_links(canonical_event_key):
    """Loads the links to the canonical event that do not have a record in the CEC table."""

    cecs = db_session.query(CodeEventCreator).\
        join(CanonicalEventLink, CodeEventCreator.id == CanonicalEventLink.cec_id).\
        join(CanonicalEvent, CanonicalEventLink.canonical_id == CanonicalEvent.id).\
        filter(CanonicalEvent.key == canonical_event_key, CodeEventCreator.variable == 'link').all()

    links = list(set([cec.article_id for cec in cecs]))
        
    return links


@app.route('/_store_recent_events')
@login_required
def _store_recent_events(cand_event_ids, canonical_event_key):
    """ Stores the recent events. Occurs with the grid reload. """

    if cand_event_ids:
        for ce_id in cand_event_ids:
            ## load recent events for this user
            events = db_session.query(RecentEvent).\
                filter(
                    RecentEvent.event_id == ce_id, 
                    RecentEvent.coder_id == current_user.id
                ).order_by(desc(RecentEvent.last_accessed)).all()

            ## if there's more than one event record, delete the oldest ones
            if len(events) > 1:
                for event in events[1:]:
                    db_session.delete(event)
                    db_session.commit()
            elif len(events) == 1:
                events[0].last_accessed = dt.datetime.now()
                db_session.add(events[0])
                db_session.commit()
            else:
                event = RecentEvent(current_user.id, ce_id)
                db_session.add(event)
                db_session.commit()
    
    if canonical_event_key:
        ## load the canonical event
        canonical_id = db_session.query(CanonicalEvent).\
            filter(CanonicalEvent.key == canonical_event_key).first().id

        ## load recent events for this user
        events = db_session.query(RecentCanonicalEvent).\
            filter(
                RecentCanonicalEvent.canonical_id == canonical_id, 
                RecentCanonicalEvent.coder_id == current_user.id
            ).order_by(desc(RecentCanonicalEvent.last_accessed)).all()

        ## if there's more than one canonical event record, delete the oldest ones
        if len(events) > 1:
            for event in events[1:]:
                db_session.delete(event)
                db_session.commit()
        elif len(events) == 1:
            events[0].last_accessed = dt.datetime.now()
            db_session.add(events[0])
            db_session.commit()
        else:
            event = RecentCanonicalEvent(current_user.id, canonical_id)
            db_session.add(event)
            db_session.commit()

    return None

#####
##### Pagination helpers
#####

class Pagination(object):
    """
    Extracted from flask-sqlalchemy
    Internal helper class returned by :meth:`BaseQuery.paginate`.  You
    can also construct it from any other SQLAlchemy query object if you are
    working with other libraries.  Additionally it is possible to pass `None`
    as query object in which case the :meth:`prev` and :meth:`next` will
    no longer work.
    """

    def __init__(self, query, page, per_page, total, items):
        #: the unlimited query object that was used to create this
        #: pagination object.
        self.query = query
        #: the current page number (1 indexed)
        self.page = page
        #: the number of items to be displayed on a page.
        self.per_page = per_page
        #: the total number of items matching the query
        self.total = total
        #: the items for the current page
        self.items = items

    @property
    def pages(self):
        """The total number of pages"""
        if self.per_page == 0:
            pages = 0
        else:
            pages = int(math.ceil(self.total / float(self.per_page)))
        return pages

    def prev(self, error_out=False):
        """Returns a :class:`Pagination` object for the previous page."""
        assert self.query is not None, 'a query object is required ' \
                                       'for this method to work'
        return paginate(self.query, self.page - 1, self.per_page, error_out)

    @property
    def prev_num(self):
        """Number of the previous page."""
        return self.page - 1

    @property
    def has_prev(self):
        """True if a previous page exists"""
        return self.page > 1

    def next(self, error_out=False):
        """Returns a :class:`Pagination` object for the next page."""
        assert self.query is not None, 'a query object is required ' \
                                       'for this method to work'
        return paginate(self.query, self.page + 1, self.per_page, error_out)

    @property
    def has_next(self):
        """True if a next page exists."""
        return self.page < self.pages

    @property
    def next_num(self):
        """Number of the next page"""
        return self.page + 1

    def iter_pages(self, left_edge=2, left_current=2,
                   right_current=5, right_edge=2):
        """Iterates over the page numbers in the pagination.  The four
        parameters control the thresholds how many numbers should be produced
        from the sides.  Skipped page numbers are represented as `None`.
        This is how you could render such a pagination in the templates:
        .. sourcecode:: html+jinja
            {% macro render_pagination(pagination, endpoint) %}
              <div class=pagination>
              {%- for page in pagination.iter_pages() %}
                {% if page %}
                  {% if page != pagination.page %}
                    <a href="{{ url_for(endpoint, page=page) }}">{{ page }}</a>
                  {% else %}
                    <strong>{{ page }}</strong>
                  {% endif %}
                {% else %}
                  <span class=ellipsis>…</span>
                {% endif %}
              {%- endfor %}
              </div>
            {% endmacro %}
        """
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and \
                num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num

def paginate(query, page, per_page=20, error_out=True):
    """
    Modified from the flask-sqlalchemy to support paging for
    the original version of the sqlalchemy that not use BaseQuery.
    """
    if page < 1 and error_out:
        abort(404)

    items = query.limit(per_page).offset((page - 1) * per_page).all()
    if not items and page != 1 and error_out:
        abort(404)

    # No need to count if we're on the first page and there are fewer
    # items than we expected.
    if page == 1 and len(items) < per_page:
        total = len(items)
    else:
        total = query.order_by(None).count()

    return Pagination(query, page, per_page, total, items)

def url_for_other_page(page):
    args = request.view_args.copy()
    args['page'] = page
    return url_for(request.endpoint, **args)

app.jinja_env.globals['url_for_other_page'] = url_for_other_page

@app.route('/code2queue/<sort>/<sort_dir>')
@app.route('/code2queue/<sort>/<sort_dir>/<int:page>')
@login_required
def code2queue(sort, sort_dir, page = 1):
    if current_user.authlevel < 2:
        return redirect(url_for('index'))

    ## get existing queue items to note which ones are coded
    spqs = {spq.article_id: 1 for spq in db_session.query(SecondPassQueue).filter(SecondPassQueue.coded_dt != None).all()}

    ## get coding info
    cfp_dict  = {}
    cfp_order = []

    pagination = paginate(db_session.query(CodeFirstPass, ArticleMetadata)
                            .join(ArticleMetadata)
                            .filter(CodeFirstPass.variable == 'protest'),
                            page, 10000, True)
    for cfp, am in pagination.items:
        pub = ''
        if 'AGW' in am.db_id:
            pub = "-".join(am.db_id.split("_")[0:2])
        elif 'NYT' in am.db_id:
            pub = 'NYT'
        else:
            pub = am.db_id.split("_")[0]

        if cfp.article_id not in cfp_dict:
            cfp_dict[cfp.article_id] = {"coder_value": [], "pub": pub, "percent_yes": 0, "percent_maybe": 0, "percent_no": 0}

        ## set css class
        cfp_dict[cfp.article_id]["coder_value"].append( (cfp.coder_id, cfp.value) )
        cfp_order.append(cfp.article_id)

    ## add metadata and delete all nos
    for article_id, v in cfp_dict.items():
        to_del = True
        for coder, decision in v["coder_value"]:
            ## not sure why this would be null, but it is
            if not decision:
                continue

            ## filter out articles in which all users said no
            if decision == "yes" or decision == "maybe":
                to_del = False

            ## add to percent
            cfp_dict[article_id]["percent_" + decision] += 1.

        ## divide all
        for decision in ['yes', 'no', 'maybe']:
            cfp_dict[article_id]["percent_" + decision] /= len(cfp_dict[article_id]["coder_value"])

        ## inefficient way to do listwise delete but ¯\_(ツ)_/¯
        if to_del:
            del cfp_dict[article_id]
            cfp_order.remove(article_id)

    ## sort by different variables
    if sort == 'coder_value':
        cfp_order = [x[0] for x in sorted(cfp_dict.items(), key = lambda x: len(x[1][sort]), reverse = True if sort_dir == 'desc' else False)]
    else:
        cfp_order = [x[0] for x in sorted(cfp_dict.items(), key = lambda x: x[1][sort], reverse = True if sort_dir == 'desc' else False)]

    return render_template(
        "code2queue.html",
        cfp_dict  = cfp_dict,
        cfp_order = cfp_order,
        spqs = spqs,
        pagination = pagination)

#####
##### Coder stats
#####

@login_required
def _pubCount():
    """
        Determine yes/maybe, total coded, in for each publication

        I hate everything and am just going to do this in pandas
        get all the articles in the database.
        TODO: One day, convert this to a pure sqlalchemy solution.
    """

    df_am = pd.DataFrame([(x.id, x.db_name, x.db_id)  for x in db_session.query(ArticleMetadata).all()],\
        columns = ['article_id', 'db_name', 'db_id'])
    df_am = df_am.set_index('article_id')

    ## get all the articles in the queue
    df_aq = pd.DataFrame([(x.article_id, x.coded_dt) for x in db_session.query(ArticleQueue).all()],\
        columns = ['article_id', 'coded_dt'])

    ## note that they're in the queue
    df_aq['in_queue'] = 1
    df_aq = df_aq.set_index('article_id')

    ## note all of those which have protest values
    df_cfp = pd.DataFrame([(x.article_id, x.value) for x in db_session.query(CodeFirstPass).filter(CodeFirstPass.variable == 'protest').all()],\
        columns = ['article_id', 'protest_value'])
    df_cfp = df_cfp.set_index('article_id')

    ## do an outer join of all of the tables
    df_all = df_am.join(df_aq).join(df_cfp)

    ## fill NA with 0 for convenience
    df_all = df_all.fillna(0)

    ## Retrieve publication name
    df_all['publication'] = df_all.apply(lambda x: convertIDToPublication(x['db_id'], x['db_name']), axis = 1)

    ## calculate various counts per publication
    ## 1. Number of unique articles which have been labeled yes/maybe
    ## 2. Total number of articles coded
    ## 3. Articles remaining in user queues
    ## 4. Remaining number of articles which are in the database but aren't in a queue/haven't been coded
    gr        = df_all.groupby(['publication'])
    total     = {'yes_maybe': 0, 'coded': 0, 'in_queue': 0, 'in_db': 0}
    pub_total = []
    for publication, group in gr:

        ## weird bug here
        if publication == 'id':
            continue

        ## skip DoCA
        if publication == 'NYT':
            group = group[(group.db_name != 'DoCA') & (group.db_name != 'LDC')]

        yes_maybe = group[(group.protest_value == 'yes') | (group.protest_value == 'maybe')].db_id.nunique()
        coded     = group[group.coded_dt == group.coded_dt].db_id.nunique()
        in_queue  = group[(group.in_queue == 1) & (group.coded_dt != group.coded_dt)].db_id.nunique()
        in_db     = group[group.in_queue != 1].db_id.nunique()

        pub_total.append( (publication, yes_maybe, coded, in_queue, in_db ) )

        total['yes_maybe'] += yes_maybe
        total['coded']     += coded
        total['in_queue']  += in_queue
        total['in_db']     += in_db

    ## Generate total
    pub_total.append( ('Total', total['yes_maybe'], total['coded'], total['in_queue'], total['in_db']) )
    return pub_total


@login_required
def _codedOnce():
    """ Count all articles which have only been coded once, by coder. """

    ## get all coded articles
    df_cq = pd.DataFrame([(x[0].article_id, x[1].username) \
        for x in db_session.query(ArticleQueue, User).join(User).filter(ArticleQueue.coded_dt != None).all()],\
        columns = ['article_id', 'coder_id'])

    ## count number of times article has been coded
    gr = df_cq.groupby('article_id').agg(np.count_nonzero)
    gr.columns = ['count']

    ## get all those articles only coded once
    df_us = df_cq[df_cq.article_id.isin(gr[gr['count'] == 1].index)].copy()
    gr    = df_us.groupby('coder_id').agg(np.count_nonzero).reset_index()

    ## make tuple of counts, add total
    coded_once = [tuple(x) for x in gr.values]
    coded_once.append( ('total', np.sum(gr['article_id'])) )

    return coded_once


@app.route('/admin')
@login_required
def admin():
    if current_user.authlevel < 3:
        return redirect(url_for('index'))

    ura   = {u.id: u.username for u in db_session.query(User).filter(User.authlevel == 1).all()}
    coded = {user: {} for user in ura.keys()}
    dbs   = [x[0] for x in db_session.query(ArticleMetadata.db_name).distinct()]
    pubs  = []

    ## get the available publications
    if app.config['STORE_ARTICLES_INTERNALLY']:
        pubquery = db_session.query(ArticleMetadata.publication).\
                   distinct().\
                   order_by(ArticleMetadata.publication)
        pubs = [row.publication for row in pubquery]
    elif app.config['SOLR']:
        url = '{}/select?q=Database:"University%20Wire"&rows=0&wt=json'.format(app.config['SOLR_ADDR'])
        fparams = 'facet=true&facet.field=PUBLICATION&facet.limit=1000'

        if (sys.version_info < (3, 0)):
            ## Python 2
            import urllib2
            req  = urllib2.Request(url + '&' + fparams)
            res  = urllib2.urlopen(req)
        else:
            ## Python 3
            res = urllib.request.urlopen(url + '&' + fparams)

        jobj = json.loads(res.read())

        ## get every other entry in this list
        pubs = sorted(jobj['facet_counts']['facet_fields']['PUBLICATION'][0::2])

    ## get user stats for EC
    for count, user in db_session.query(func.count(EventCreatorQueue.id), User.id).\
        join(User).group_by(User.id).filter(EventCreatorQueue.coded_dt == None, User.id.in_(ura.keys())).all():
        coded[user]['remaining'] = count

    for count, user in db_session.query(func.count(EventCreatorQueue.id), User.id).\
        join(User).group_by(User.id).filter(EventCreatorQueue.coded_dt != None, User.id.in_(ura.keys())).all():
        coded[user]['completed'] = count

    ## get number of unassigned articles
    ## TODO: Eventually generate this count for publications
    unassigned = []
    #all_metadata = db_session.query(ArticleMetadata).all()
    #assigned_metadata = db_session.query(EventCreatorQueue).all()

    for db in dbs:
        unassigned.append( (db, len( set([x.id for x in db_session.query(ArticleMetadata).filter_by(db_name = db).all()]) - \
        set([x[0] for x in db_session.query(distinct(EventCreatorQueue.article_id)).all()]))) )

    return render_template(
        "admin.html",
        coded      = coded,
        ura        = ura,
        dbs        = dbs,
        unassigned = unassigned,
        pubs       = pubs
    )


@app.route('/coderstats')
@login_required
def coderStats():
    ## get last week datetime
    last_week  = dt.datetime.now(tz = central) - dt.timedelta(weeks=1)
    pub_total  = []
    coded_once = None
    pub_total  = None
    passes     = ['1', '2', 'ec']
    stats      = ['completed', 'lw', 'remaining', 'dt']
    models     = [ArticleQueue, SecondPassQueue, EventCreatorQueue]
    if current_user.authlevel < 3:
        ## show own stats if not an admin
        ura = [current_user.username]
        gra = [current_user.username]

        last_cfp = None
        last_csp = None
        last_cec = None
    else:
        ## first pass coders
        ura = [u.username for u in db_session.query(User).filter(User.authlevel == 1).all()]

        ## Add stats for second pass coders
        gra = [u.username for u in db_session.query(User).filter(User.authlevel > 1).all()]

        ## get most recent DB updates
        last_cfp = db_session.query(CodeFirstPass, User).join(User).order_by(desc(CodeFirstPass.timestamp)).first()
        last_csp = db_session.query(CodeSecondPass, User).join(User).order_by(desc(CodeSecondPass.timestamp)).first()
        last_cec = db_session.query(CodeEventCreator, User).join(User).order_by(desc(CodeEventCreator.timestamp)).first()

    ## initialize user list
    coded = {user: {s: {p: None for p in passes} for s in stats} for user in ura[:] + gra[:]}

    ## get total articles coded
    for i in range(len(passes)):
        pn = passes[i]
        for count, user in db_session.query(func.count(models[i].id), User.username).\
            join(User).group_by(User.username).filter(models[i].coded_dt != None, User.username.in_(ura)).all():
            coded[user]['completed'][pn] = count

        for count, user in db_session.query(func.count(models[i].id), User.username).\
            join(User).group_by(User.username).filter(models[i].coded_dt > last_week, User.username.in_(ura)).all():
            coded[user]['lw'][pn] = count

        ## remaining articles in queue
        for count, user in db_session.query(func.count(models[i].id), User.username).\
            join(User).group_by(User.username).filter(models[i].coded_dt == None, User.username.in_(ura)).all():
            coded[user]['remaining'][pn] = count

        ## get the last time coded
        for timestamp, user in db_session.query(func.max(models[i].coded_dt), User.username).\
            join(User).group_by(models[i].coder_id).filter(models[i].coded_dt != None, User.username.in_(ura)).all():
            coded[user]['dt'][pn] = timestamp

    ## comment this out to save on a lot of load time for this page.
    if current_user.authlevel > 2:
        ## generate the publication statistics
        #pub_total = _pubCount()

        ## get the coded once counts
        #coded_once = _codedOnce()
        pass

    return render_template(
        "coder_stats.html",
        coded      = coded,
        pub_total  = pub_total,
        last_cfp   = last_cfp,
        last_csp   = last_csp,
        last_cec   = last_cec,
        pn         = 'ec',
        pass_title = 'Event Creator Status',
        ura        = ura,
        gra        = gra,
        coded_once = coded_once
    )

@app.route('/publications')
@app.route('/publications/<sort>')
@login_required
def publications(db):
    """
      Generate list of all publications and all articles remaining. 
    """
    if current_user.authlevel < 3:
        return redirect(url_for('index'))

    ## TODO: Write code to sort by selected attribute
    
    query = """
    SELECT REPLACE(REPLACE(dem.publication, '-', ' '), '   ', ' - ') as publication, 
    COALESCE(num.in_queue,0) as in_queue, 
    dem.total as total,
    IF(in_queue IS NULL OR in_queue = 0, total, total - in_queue) AS to_be_coded 
    FROM
    (
    SELECT SUBSTRING_INDEX(am.db_id, '_', 1) as publication, COUNT(*) AS in_queue
    FROM article_metadata am
    WHERE am.db_name = '%s' AND am.id IN (SELECT article_id FROM event_creator_queue)
    GROUP BY 1
) num RIGHT JOIN
(
    SELECT SUBSTRING_INDEX(am.db_id, '_', 1) as publication, COUNT(*) AS total
    FROM article_metadata am
    WHERE db_name = '%s'
    GROUP BY 1
) dem ON num.publication = dem.publication
ORDER BY to_be_coded DESC, total DESC
    """
    
    result = db_session.execute(query)
    rows = [(row[0], row[1], row[2], row[3]) for row in result]

    return render_template("publications.html", pub_list = rows)

    
@app.route('/userarticlelist/<pn>')
@app.route('/userarticlelist/<pn>/<int:page>')
@login_required
def userArticleList(pn, page = 1):
    """ View for coders to see their past articles. """
    model = None
    if pn == '1':
        model = ArticleQueue
    elif pn == '2':
        model = SecondPassQueue
    elif pn =='ec':
        model = EventCreatorQueue
    else:
        return make_response("Invalid page.", 404)

    pagination = paginate(db_session.query(model, ArticleMetadata).\
            filter(model.coder_id == current_user.id, model.coded_dt != None).\
            join(ArticleMetadata).\
            order_by(desc(model.coded_dt)), page, 10000, True)

    return render_template("list.html", 
                           pn  = pn,
                           aqs = pagination.items,
                           pagination = pagination)


@app.route('/userarticlelist/admin/<is_coded>/<coder_id>/<pn>')
@app.route('/userarticlelist/admin/<is_coded>/<coder_id>/<pn>/<int:page>')
@login_required
def userArticleListAdmin(coder_id, is_coded, pn, page = 1):
    """ View for admins to manually inspect specific coder queues. """
    if current_user.authlevel < 3:
        return redirect(url_for('index'))

    model = None
    if pn == '1':
        model = ArticleQueue
    elif pn == '2':
        model = SecondPassQueue
    elif pn =='ec':
        model = EventCreatorQueue
    else:
        return make_response("Invalid page.", 404)

    is_coded_condition = None
    if is_coded == '0':
        is_coded_condition = model.coded_dt == None
    else:
        is_coded_condition = model.coded_dt != None

    ## show articles in the order they entered the user's queue
    pagination = paginate(db_session.query(model, ArticleMetadata).\
                     filter(model.coder_id == coder_id, is_coded_condition).\
                     join(ArticleMetadata).\
                     order_by(model.id), page, 10000, True)
    username = db_session.query(User).filter(User.id == int(coder_id)).first().username

    return render_template("list.html", 
        pn  = pn,
        aqs = pagination.items,
        is_coded = is_coded,
        username = username,
        pagination = pagination)


## generate report CSV file and store locally/download
@app.route('/_generate_coder_stats', methods=['POST'])
@login_required
def generateCoderAudit():
    if current_user.authlevel < 3:
        return redirect(url_for('index'))

    pn = request.form['pn']
    action = request.form['action']

    # last_month = dt.datetime.now(tz = central) - dt.timedelta(weeks=4)
    users = {u.id: u.username for u in db_session.query(User).all()}

    if pn == '1':
        model = CodeFirstPass
    elif pn == 'ec':
        model = CodeEventCreator
    else:
        return make_response('Invalid pass number.', 500)

    to_df = []
    cols  = [x.name for x in model.__table__.columns]
    query = db_session.query(model, ArticleMetadata).join(ArticleMetadata).all()

    if len(query) <= 0:
        return

    for row in query:
        fp  = row[0]
        am  = row[1]

        ## store all fields in a row in a tuple
        to_print = ()
        for c in cols:
            if c == 'coder_id':
                to_print += ( users[fp.__getattribute__(c)], )
            else:
                to_print += ( validate(fp.__getattribute__(c)), )

        ## add publication, publication date, and solr_id
        pub      = ''
        pub_date = ''
        solr_id  = am.db_id 
        if am.db_id is None:
            pass
        elif 'AGW' in am.db_id:
            ## e.g.
            ## AGW_AFP_ENG_20040104.0056
            pieces   = am.db_id.split("_")
            pub      = "-".join(pieces[0:3])
            pub_date   = pieces[3].split('.')[0]
            pub_date = dt.datetime.strptime(pub_date, '%Y%m%d').strftime('%Y-%m-%d')
        elif 'NYT' in am.db_id:
            ## e.g. 
            ## 1989/03/11/0230638.xml_LDC_NYT
            pub      = 'NYT'
            pub_date = am.db_id[0:10].replace('/', '-')
        else:
            ## e.g. 
            ## Caribbean-Today;-Miami_1996-12-31_26b696eae2887c8cf71735a33eb39771
            pieces   = am.db_id.split("_")
            pub      = pieces[0]
            pub_date = pieces[1]
        to_print += ( pub, pub_date, solr_id )
        to_df.append(to_print)

    cols.extend(['publication', 'pub_date', 'solr_id'])

    ## let the dataframe do all the heavy lifting for CSV formatting
    df = pd.DataFrame(to_df, columns = cols)

    if action == 'download':
        file_str = df.to_csv(None, encoding = 'utf-8', index = False)
        response = make_response(file_str)
        response.headers["Content-Disposition"] = "attachment; filename=coder-table.tsv"
        response.headers["mime-type"] = "text/csv"
        return response
    elif action == 'save':
        filename = '%s/exports/coder-table_%s.csv' % (app.config['WD'], dt.datetime.now().strftime('%Y-%m-%d_%H%M%S'))
        df.to_csv(filename, encoding = 'utf-8', index = False)
        return jsonify(result={"status": 200, "filename": filename})
    else:
        return make_response("Illegal action.", 500)

#####
##### Internal calls
#####

@app.route('/_add_article_code/<pn>', methods=['POST'])
@login_required
def addArticleCode(pn):
    """ Adds a record to article coding table. """
    aid  = int(request.form['article'])
    var  = request.form['variable']
    val  = request.form['value']
    text = request.form.get('text')
    aqs  = []
    now  = dt.datetime.now(tz = central).replace(tzinfo = None)

    if pn == 'ec':
        model = CoderArticleAnnotation
        p     = CoderArticleAnnotation(aid, var, val, current_user.id, text)

        for aq in db_session.query(EventCreatorQueue).filter_by(article_id = aid, coder_id = current_user.id).all():
            aq.coded_dt = now
            aqs.append(aq)
    else:
        return make_response("Invalid model", 404)

    ## variables which only have one value per article
    if var in sv:
        a = db_session.query(model).filter_by(
            article_id = aid,
            variable   = var,
            coder_id   = current_user.id
        ).all()

        ## if there's more then one, delete them
        if len(a) > 0:
            for o in a:
                db_session.delete(o);

            db_session.commit()

    db_session.add(p)
    db_session.add_all(aqs)
    db_session.commit()
    return make_response("", 200)


@app.route('/_del_article_code/<pn>', methods=['POST'])
@login_required
def delArticleCode(pn):
    """ Deletes a record from article coding table. """
    article  = request.form['article']
    variable = request.form['variable']
    value    = request.form['value']
    if pn == 'ec':
        a = db_session.query(CoderArticleAnnotation).filter_by(
            article_id = article,
            variable   = variable,
            value      = value,
            coder_id   = current_user.id
        ).all()
    else:
        return make_response("Invalid model", 404)

    if len(a) > 0:
        for o in a:
            db_session.delete(o)

        db_session.commit()

        return jsonify(result={"status": 200})
    else:
        return make_response("", 404)


@app.route('/_change_article_code/<pn>', methods=['POST'])
@login_required
def changeArticleCode(pn):
    """ 
        Changes a radio button or text input/area by removing all prior
        values, adds one new one.
    """
    article  = request.form['article']
    variable = request.form['variable']
    value    = request.form['value']

    ## delete all prior values
    a = db_session.query(CoderArticleAnnotation).filter_by(
        article_id = article,
        variable   = variable,
        coder_id   = current_user.id
    ).all()

    for o in a:
        db_session.delete(o)
    db_session.commit()

    ## add new value
    ac = CoderArticleAnnotation(article, variable, value, current_user.id)

    db_session.add(ac)
    db_session.commit()

    return jsonify(result={"status": 200})


@app.route('/_add_code/<pn>', methods=['POST'])
@login_required
def addCode(pn):
    aid  = int(request.form['article'])
    var  = request.form['variable']
    val  = request.form['value']
    ev   = request.form['event']
    text = request.form.get('text')
    aqs  = []
    now  = dt.datetime.now(tz = central).replace(tzinfo = None)

    if pn == '1':
        model = CodeFirstPass

        ## store highlighted text on first pass
        if text:
            p = CodeFirstPass(aid, var, val, current_user.id, text)
        else:
            p = CodeFirstPass(aid, var, val, current_user.id)

        ## update datetime on every edit
        aq = db_session.query(ArticleQueue).filter_by(article_id = aid, coder_id = current_user.id).first()
        aq.coded_dt = now
        aqs.append(aq)
    elif pn == '2':
        model = CodeSecondPass
        p     = CodeSecondPass(aid, ev, var, val, current_user.id)

        for aq in db_session.query(SecondPassQueue).filter_by(article_id = aid, coder_id = current_user.id).all():
            aq.coded_dt = now
            aqs.append(aq)
    elif pn == 'ec':
        model = CodeEventCreator
        p     = CodeEventCreator(aid, ev, var, val, current_user.id, text)

        for aq in db_session.query(EventCreatorQueue).filter_by(article_id = aid, coder_id = current_user.id).all():
            aq.coded_dt = now
            aqs.append(aq)
    else:
        return make_response("Invalid model", 404)

    ## variables which only have one value per article
    if var in sv:
        if pn == '1':
            a = db_session.query(model).filter_by(
                article_id = aid,
                variable   = var,
                coder_id   = current_user.id
            ).all()
        else:
            ## for second pass and event coder, filter for distinct event
            a = db_session.query(model).filter_by(
                article_id = aid,
                variable   = var,
                event_id   = ev,
                coder_id   = current_user.id
            ).all()

        ## if there's more then one, delete them
        if len(a) > 0:
            for o in a:
                db_session.delete(o);

            db_session.commit()

    ## if this is a 2nd comment pass comment and it is null, skip it
    if var == 'comments' and pn == '2' and val == '':
        return jsonify(result={"status": 200})

    db_session.add(p)
    db_session.add_all(aqs)
    db_session.commit()
    return make_response("", 200)


@app.route('/_del_event', methods=['POST'])
@login_required
def delEvent():
    """ Delete an event. """
    eid = int(request.form['event'])
    pn  = request.form['pn'];

    model = None
    if pn == '2':
        model = CodeSecondPass
    elif pn == 'ec':
        model = CodeEventCreator
    else:
        return make_response("Invalid model.", 404)

    db_session.query(model).filter_by(event_id = eid).delete()
    db_session.query(Event).filter_by(id = eid).delete()

    db_session.commit()

    return make_response("Delete succeeded.", 200)


@app.route('/_del_code/<pn>', methods=['POST'])
@login_required
def delCode(pn):
    """ Deletes a record from coding tables. """
    article  = request.form['article']
    variable = request.form['variable']
    value    = request.form['value']
    event    = request.form['event']

    if False:
        pass
    elif pn == '1':
        a = db_session.query(CodeFirstPass).filter_by(
            article_id = article,
            variable   = variable,
            value      = value,
            coder_id   = current_user.id
        ).all()
    elif pn == '2':
        a = db_session.query(CodeSecondPass).filter_by(
            article_id = article,
            variable   = variable,
            value      = value,
            event_id   = event,
            coder_id   = current_user.id
        ).all()
    elif pn == 'ec':
        a = db_session.query(CodeEventCreator).filter_by(
            article_id = article,
            variable   = variable,
            value      = value,
            event_id   = event,
            coder_id   = current_user.id
        ).all()
    else:
        return make_response("Invalid model", 404)

    if len(a) == 1:
        for o in a:
            db_session.delete(o)

        db_session.commit()

        return jsonify(result={"status": 200})
    elif len(a) > 1:
        return make_response(" Leave duplicates in so we can collect data on this bug.", 500)
    else:
        return make_response("", 404)


@app.route('/_change_code/<pn>', methods=['GET', 'POST'])
@login_required
def changeCode(pn):
    """ 
        Changes a radio button by removing all prior values, adds one new one. 
        Only implemented for event creator right now.
    """
    article  = request.form['article']
    variable = request.form['variable']
    value    = request.form['value']
    event    = request.form['event']

    ## delete all prior values
    a = db_session.query(CodeEventCreator).filter_by(
        article_id = article,
        variable   = variable,
        event_id   = event,
        coder_id   = current_user.id
    ).all()

    for o in a:
        db_session.delete(o)
    db_session.commit()

    ## add new value
    ec = CodeEventCreator(article, event, variable, value, current_user.id) 

    db_session.add(ec)
    db_session.commit()

    return jsonify(result={"status": 200})


@app.route('/_mark_ec_done', methods=['POST'])
@login_required
def markECDone():
    article_id = request.form['article_id']
    coder_id   = current_user.id
    now        = dt.datetime.now(tz = central).replace(tzinfo = None)

    ## update time, commit
    ecq = db_session.query(EventCreatorQueue).filter_by(article_id = article_id, coder_id = coder_id).first()
    ecq.coded_dt = now

    db_session.add(ecq)
    db_session.commit()

    return jsonify(result={"status": 200})


@app.route('/_mark_sp_done', methods=['POST'])
@login_required
def markSPDone():
    if current_user.authlevel < 2:
        return redirect(url_for('index'))

    article_id = request.form['article_id']
    coder_id   = current_user.id
    now        = dt.datetime.now(tz = central).replace(tzinfo = None)

    ## update time, commit
    spq = db_session.query(SecondPassQueue).filter_by(article_id = article_id, coder_id = coder_id).first()
    spq.coded_dt = now

    db_session.add(spq)
    db_session.commit()

    return make_response("", 200)


@app.route('/_add_queue/<pn>')
@login_required
def addQueue(pn):
    if current_user.authlevel < 2:
        return redirect(url_for('index'))

    article_id = request.args.get('article_id')
    coder_id   = request.args.get('coder_id')

    ## if this doesn't exist, add it
    if not db_session.query(SecondPassQueue).filter_by(article_id = article_id, coder_id = coder_id).count():
        spq = SecondPassQueue(article_id = article_id, coder_id = coder_id)

        db_session.add(spq)
        db_session.commit()

    return jsonify(result={"status": 200})


@app.route('/_get_events')
@login_required
def getEvents():
    aid  = int(request.args.get('article_id'))
    pn   = request.args.get('pn')
    evs  = []

    model = None
    if pn == '2':
        model = CodeSecondPass
    elif pn == 'ec':
        model = CodeEventCreator
    else:
        return make_response("Not a valid model.", 404)

    ## get a summary of the existing events for this article
    for event in db_session.query(Event).filter(Event.article_id == aid).all():

        if pn == '2':
            rvar = {'loc': [], 'form': []}
        elif pn == 'ec':
            rvar = {'desc': [], 'article-desc': []}

        yes_nos = []
        ev = {}
        ev['id'] = event.id

        codes = db_session.query(model).\
            filter_by(event_id = event.id, coder_id = current_user.id).\
            order_by(model.variable).all()

        if len(codes) == 0:
            continue

        ## get the fields in rvar
        for code in codes:
            if code.variable in rvar.keys():
                ## otherwise, just use the value
                rvar[code.variable].append(code.value)
        
        if pn == '2':
            ev['repr'] = ", ".join(rvar['loc']) + '-' + ', '.join(rvar['form'])
        elif pn =='ec':
            if len(rvar['desc']) > 0 and len(rvar['desc'][0]) > 0:
                ev['repr'] = ", ".join(rvar['desc'])
            ## No longer necessary with article-level description
            elif (len(rvar['article-desc']) > 0
                  and len(rvar['article-desc'][0]) > 0
                  and not app.config['ANNOTATE_ARTICLE_LEVEL']):
                ev['repr'] = "(no event description): " + ", ".join(rvar['article-desc'])
            else:
                ev['repr'] = "(no event description)"

        evs.append(ev)

    return jsonify({'events': evs})


@app.route('/_get_codes')
@login_required
def getCodes():
    aid   = int(request.args.get('article'))
    pn    = request.args.get('pn')
    ev    = request.args.get('event')
    l_i   = 0

    model = None
    if pn == '1':
        model = CodeFirstPass
    elif pn == '2':
        model = CodeSecondPass
    elif pn == 'ec':
        model = CodeEventCreator

    ## load current values
    curr = db_session.query(model).\
           filter_by(coder_id = current_user.id, event_id = ev, article_id = aid).all()
    cd   = {}

    for c in curr:
        ## these will occur only once
        if c.variable in sv:
            cd[c.variable] = c.value
        else:
            ## if they've seen this article before, note which pass it is
            if c.variable == 'load':
                l_i = int(c.value) + 1

            if c.variable in multi_vars_keys:
                ## stash in array
                if c.variable not in cd:
                    cd[c.variable] = []

                cd[c.variable].append( (c.value, c.text) )

    ## insert row for every time they load the article
    ## to measure how much time it takes to read the article
    if pn == '1':
        load = CodeFirstPass(aid, "load", l_i, current_user.id)
        db_session.add(load)
        db_session.commit() 

    return jsonify(cd)


@app.route('/_load_article_annotation_block')
@login_required
def modifyArticleAnnotations():
    aid  = int(request.args.get('article_id'))
    pn   = request.args.get('pn')
    curr = {}

    model = None
    if pn == 'ec':
        model = CoderArticleAnnotation
        template = 'article-annotation-block.html'
    else:
        return make_response("Not a valid model.", 404)

    ## get the current values
    for annotation in db_session.query(model).filter_by(article_id = aid, coder_id = current_user.id).all():
        if annotation.variable in sv or annotation.variable in event_creator_single_value:
            curr[annotation.variable] = annotation.value
        else:
            ## stash in array
            if annotation.variable not in curr:
                curr[annotation.variable] = []

            ## loads the items which do not have text, which means
            ## everything but text selects
            if annotation.text is None:
                curr[annotation.variable].append(annotation.value)

    return render_template(template, 
            curr = curr)

@app.route('/_load_event_block')
@login_required
def modifyEvents():
    # if current_user.authlevel < 2:
    #     return redirect(url_for('index'))

    eid  = request.args.get('event_id')
    aid  = int(request.args.get('article_id'))
    pn   = request.args.get('pn')
    opts = {}
    curr = {}

    model = None
    if pn == '2':
        model = CodeSecondPass
        template = 'event-block.html'
    elif pn == 'ec':
        model = CodeEventCreator
        template = 'event-creator-block.html'
    else:
        return make_response("Not a valid model.", 404)

    ## initialize drop-down options
    opts = {v[0]: [] for v in vars}

    if eid:
        eid = int(eid)
        ## get the current values
        for code in db_session.query(model).filter_by(event_id = eid, coder_id = current_user.id).all():
            if code.variable in sv or code.variable in event_creator_single_value:
                curr[code.variable] = code.value
            else:
                ## stash in array
                if code.variable not in curr:
                    curr[code.variable] = []

                ## loads the items which do not have text, which means
                ## everything but text selects
                if code.text is None:
                    curr[code.variable].append(code.value)

    else:
        ## add a new event
        ev  = Event(aid)
        db_session.add(ev)
        db_session.commit()

        eid = ev.id

    ## unordered presets options
    ## sorted alphabetically
    for key in sorted(preset_vars.keys()):
        for val in preset_vars[key]:
            opts[ key ].append(val)

    ## ordered presets -- uses the sorting in the YAML file
    ## used for university responses and police actions in campus protest project
    for key in preset2_vars.keys():
        for val in preset2_vars[key]:
            opts[ key ].append(val)

    ## None of the above for v1 variables
    if pn in ['1', '2']:
        for k,v in v2:
            ## coder 1-generated dropdown options
            for o in db_session.query(CodeFirstPass).filter_by(variable = k, article_id = aid).all():
                opts[ o.variable ].append(o.text)

            ## coder 2-generated dropdown options
            for o in db_session.query(CodeSecondPass).filter_by(variable = k, article_id = aid, coder_id = current_user.id).all():
                opts[ o.variable ].append(o.value)

        ## filter out repeated items and sort
        for k in opts.keys():
            opts[k] = list( set( map(lambda x: x.strip(" .,"), opts[k]) ) )
            opts[k].sort()

    return render_template(template, 
            v1 = v1, 
            v2 = v2,
            v4 = v4,
            vars = event_creator_vars,
            yes_no_vars = yes_no_vars,
            state_and_territory_vals = state_and_territory_vals,
            opts = opts, 
            curr = curr, 
            event_id = eid)


@app.route('/dynamic_form')
@login_required
def dynamic_form():
    aid = 23317
    article = db_session.query(ArticleMetadata).filter_by(id=aid).first()
    text, html = prepText(article)

    aq = db_session.query(ArticleQueue).filter_by(coder_id=current_user.id, article_id=aid).first()

    return render_template("dynamic_form.html", vars=vars, aid=aid, text=html.decode('utf-8'))


@app.route('/form_template_management')
@login_required
def form_template_management():
    return render_template("form_template_manager.html")


@app.route('/_highlight_var')
@login_required
def highlightVar():
    """
    Highlights first-pass coding. 
    Adds intensity for text selected multiple times.

    Algorithm:
    For each first-pass entry
        Store every boundary (both start and end) in a hashtable with a list.
    For each paragraph:
        state <- 0
        Sort boundaries
        For each boundary:
            For each item in the boundary list:
                if item == start
                    state <- state + 1
                else item == end
                    state <- state - 1

            if this is the last boundary
                use closing span
            if this boundary has a start and isn't the first item, or has an end
                use closing span
            else
                use opening span

            add the tag to the existing text

    add edited paragraph to paragraph list

    """
    if current_user.authlevel < 2:
        return redirect(url_for('index'))

    aid       = int(request.args.get('article'))
    var       = request.args.get('variable')
    body,html = prepText(db_session.query(ArticleMetadata).filter_by(id = aid).first())
    text_para = body.strip().split("\n")
    paras     = {}
    bounds    = {}
    r_paras   = {}
    r_meta    = {}
    meta      = html.strip().split("\n")[1]\
        .replace("<p class='meta' id='meta'>", "")\
        .replace("</p>", "")

    ## initialize
    for p_key in range(0, len(text_para)):
        p_str = str(p_key)
        bounds[p_str] = {}
        paras[p_str]  = text_para[p_key]

    paras['meta']  = meta
    bounds['meta'] = {}

    ## collect all the start and ends
    cfps = db_session.query(CodeFirstPass).filter_by(article_id = aid, variable = var).order_by('value').all()
    for cfp in cfps:
        ## trash the existing numbers, use find
        p    = cfp.value.split("-")[0]
        text = cfp.text

        ## find the first instance of the text
        ## mark as the start
        start = paras[p].find(text.encode('utf-8'))

        ## um this should happen but okay
        if start == -1:
            continue

        ## mark the end as the start plus the offset
        end   = start + len(text)

        ## add a list to the index
        ## and the type of bound it is
        if start not in bounds[p]:
            bounds[p][start] = []
        bounds[p][start].append('start')

        ## and vice versa with the end
        if end not in bounds[p]:
            bounds[p][end] = []
        bounds[p][end].append('end')

    ## based on the depth of highlighting, mark with the correct class
    for p_key, para in paras.items():
        state  = 0
        last_i = 0
        r_para = ""

        keys = bounds[p_key].keys()
        if len(keys) > 0:
            ## sort so we can go in order
            keys = sorted(keys)
        else:
            ## no highlights
            r_para = para

        for bound_index in keys:
            st_tag = ""
            en_tag = ""

            ## treat this like a state machine: if we are entering a highlight, increment the class
            ## if we are exiting a highlight, decrement it
            (has_start, has_end) = (False, False)
            for type_bound in bounds[p_key][bound_index]:
                if type_bound == 'start':
                    state += 1
                    has_start = True
                elif type_bound == 'end':
                    state -= 1
                    has_end = True

            tag = ""
            if bound_index == keys[-1]:
                en_tag = "</span>"
            else:
                if has_end:
                    en_tag = "</span>"
                if has_start:
                    if last_i != 0:
                        en_tag = "</span>"
                st_tag = "<span class='hl-%d'>" % state

            tag = en_tag + st_tag

            ## add the tag to the existing text
            r_para += para[last_i:bound_index] + tag

            ## if this is the last key, add the rest of the paragraph
            if bound_index == keys[-1]:
                r_para += para[bound_index:]

            last_i = bound_index

        ## add to the return array
        r_paras[p_key] = r_para

    r_body = ""
    for p_key in range(0, len(text_para)):
        p_key = str(p_key)
        r_body += "<p id='%s'>%s</p>\n" % (p_key, r_paras[p_key])

    return jsonify(result={"status": 200, "meta": r_paras['meta'], "body": r_body})


#####
##### ADMIN TOOLS
#####

@app.route('/_add_user', methods=['POST'])
@login_required
def addUser():
    if current_user.authlevel < 3:
        return redirect(url_for('index'))

    username = request.form['username']

    ## validate
    if not re.match(r'[A-Za-z0-9_]+', username):
        return make_response('Invalid username. Use only letters, numbers, and underscores.', 500)

    exists = db_session.query(User).filter_by(username = username).first()
    if exists:
        return make_response('Username exists. Choose another.', 500)

    ## generate password
    chars    = string.ascii_letters + string.digits
    length   = 8
    password = ''.join([choice(chars) for i in range(length)])

    db_session.add(User(username = username, password = password, authlevel = 1))
    db_session.commit()

    ## TODO: Send email to admin to have notice of new account

    return jsonify(result={"status": 200, "password": password})


@app.route('/_assign_articles', methods=['POST'])
@login_required
def assignArticles():
    if current_user.authlevel < 3:
        return redirect(url_for('index'))

    num     = request.form['num']
    db_name = request.form['db']
    pub     = request.form['pub']
    ids     = request.form['ids']
    users   = request.form['users']
    same    = request.form['same']
    group_size = request.form['group_size']
    
    ## input validations
    if num == '' and ids == '':
        return make_response('Please enter a valid number of articles or a list of IDs.', 500)
    if num != '' and ids != '':
        return make_response('You can either enter a number of articles or a list of IDs, but not both.', 500)
    if db_name == '' and pub == '' and ids == '':
        return make_response('Please select a valid database or publication, or enter a list of IDs.', 500)
    if db_name != '' and pub != '':
        return make_response('You can only choose a database or publication, but not both.', 500)
    if same is None and group_size == '':
        return make_response('Please select a "same" or "different" option, or enter a group size number.', 500)
    if same is not None and group_size != '':
        return make_response('You can only choose same/different or a group size. Force reload the page to reset same/different.', 500)
    if num != '':
        try:
            num = int(num)
        except:
            return make_response('Please enter a valid number of articles.', 500)

        ## get number of unassigned articles
        if pub:
            pub = "-".join(pub.split())
            full_set = set([x.id for x in db_session.query(ArticleMetadata).\
                            filter(ArticleMetadata.db_id.like('%s%%' % pub)).all()])
        else:
            full_set = set([x.id for x in db_session.query(ArticleMetadata).\
                            filter_by(db_name = db_name).all()])

        assigned   = set([x[0] for x in db_session.query(distinct(EventCreatorQueue.article_id)).all()])
        unassigned = len( full_set - assigned )

        if num > unassigned:
            return make_response('Select a number less than or equal to number of unassigned articles.', 500)

    if users == '':
        return make_response('Please select some users.', 500)

    user_ids = map(lambda x: int(x), users.split(','))

    if group_size != '':
        try:
            group_size = int(group_size)
        except:
            return make_response('Please enter a valid group size.', 500)

        if len(user_ids) <= group_size:
            return make_response('Number of users must be greater than k.', 500)

    n_added = 0
    ## assign a number of articles
    if ids == '':
        ## assign by individual
        if group_size == '':
            if same == 'same':
                ## assign by database
                if db_name:
                    articles = assign_lib.generateSample(num, db_name, 'ec')
                else:
                    ## assign by publication
                    articles = assign_lib.generateSample(num, None, 'ec', pub)

                n_added = assign_lib.assignmentToCoders(articles, user_ids, 'ec')
            elif same == 'different':
                for u in user_ids:
                    if db_name:
                        articles = assign_lib.generateSample(num, db_name, 'ec')
                    else:
                        articles = assign_lib.generateSample(num, None, 'ec', pub)
                    n_added  += assign_lib.assignmentToCoders(articles, [u], 'ec')
        else:
            ## assignment by bin
            bins       = assign_lib.createBins(user_ids, group_size)
            num_sample = assign_lib.generateSampleNumberForBins(num, len(user_ids), group_size)
            if db_name:
                articles = assign_lib.generateSample(num_sample, db_name, pass_number = 'ec')
            else: 
                articles = assign_lib.generateSample(num, None, 'ec', pub)
            assign_lib.assignmentToBin(articles, bins, pass_number = 'ec')
            n_added = len(articles)
    else: 
        ## assignment by ID
        if group_size:
            ## can't assign by ID because of the factorial math
            return make_response('Cannot assign articles by ID with bins.', 500)

        ids = map(lambda x: int(x), ids.strip().split('\n'))
        if same == 'same':
            n_added = assign_lib.assignmentToCoders(ids, user_ids, 'ec')
        elif same == 'different':
            return make_response('Can only assign the same articles by ID.', 500)

    return make_response('%d articles assigned successfully.' % n_added, 200)


@app.route('/_transfer_articles', methods=['POST'])
@login_required
def transferArticles():
    if current_user.authlevel < 3:
        return redirect(url_for('index'))

    num        = request.form['num']
    from_users = request.form['from_users']
    to_users   = request.form['to_users']

    try:
        num = int(num)
    except:
        return make_response('Please enter a valid number.', 500)
   
    from_users = map(lambda x: int(x), from_users.split(','))
    to_users = map(lambda x: int(x), to_users.split(','))

    n = assign_lib.transferCoderToCoder(from_users, to_users, 'ec', num)

    return make_response('%d articles transferred successfully.' % n, 200)


@app.route('/_search_solr')
@login_required
def searchSolr():
    if current_user.authlevel < 3:
        return redirect(url_for('index'))

    database    = request.args.get('database')
    publication = request.args.get('publication')
    start_date  = request.args.get('start-date')
    end_date    = request.args.get('end-date')
    search_str  = request.args.get('search-string')
    solr_ids    = request.args.get('solr-ids')

    if (database == '---' and publication != '') or (database != '' and publication == '---'):
        return make_response('Choose either a database or publication.', 500)

    ## build query
    query = []

    ## choose correct database field
    if database:
        if database in ['Annotated Gigaword v5', 'LDC']:
            query.append('DOCSOURCE:"%s"' % database)
        elif database == 'Ethnic NewsWatch':
            query.append('Database:"%s"' % database)
        else:
            return make_response('Invalid database.', 500)

    if start_date == '' and end_date != '':
        return make_response('End date needs a matching start date.', 500)

    if publication:
        query.append('PUBLICATION:"%s"' % publication)

    if start_date:
        ## set end date to now
        if not end_date:
            end_date = dt.datetime.now().strftime('%Y-%m-%d')

        query.append('DATE:[%sT00:00:00.000Z TO %sT00:00:00.000Z]' % (start_date, end_date))

    if search_str:
        query.append('(%s)' % search_str)

    if solr_ids:
        query.append('id:(%s)' % " ".join(solr_ids.split('\n')))

    qstr = ' AND '.join(query)

    return make_response(qstr, 200)

if __name__ == '__main__':
    app.run()
