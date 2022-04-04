import pandas as pd
import numpy as np
import sqlalchemy

import os
import sys
import yaml

sys.path.insert(0, os.path.join(os.path.abspath('.'), 'scripts'))

from context import config

## MySQL setup
mysql_engine = sqlalchemy.create_engine(
    'mysql://%s:%s@localhost/%s?unix_socket=%s&charset=%s' % 
        (config.MYSQL_USER, 
        config.MYSQL_PASS, 
        config.MYSQL_DB, 
        config.MYSQL_SOCK, 
        'utf8mb4'))

## skip these users
skip_users = ['test1', 'admin', 'tina', 'alex', 'ellen', 'ishita', 
    'andrea', 'karishma', 'Eloya', 'Khadro']

## get the disqualifying information rows
disqualifying_variables = yaml.load(
            open('../yes-no.yaml', 'r'), 
            Loader = yaml.BaseLoader)
disqualifying_variables = [x[0] for x in disqualifying_variables['Disqualifying information']]

## sideload hand-curated decision list and take first two columns
df_decisions = pd.read_csv('../hand/Decisions on specific articles - use for adjudication - Decisions Snapshot (2022-01-20).csv')
df_decisions = df_decisions[['article_id', 'event_id']]

query = """SELECT 
    cec.event_id, 
    u.username AS coder_id, 
    cec.variable, 
    cec.value, 
    cec.text, 
    am.id AS article_id,
    am.pub_date, 
    am.publication, 
    am.title,
    cec_form.form AS form,
    cec_issue.issue AS issue,
    cec_racial_issue.racial_issue as racial_issue
FROM coder_event_creator cec
LEFT JOIN article_metadata am ON (cec.article_id = am.id)  
LEFT JOIN user u ON (cec.coder_id = u.id)
LEFT JOIN (SELECT 
            event_id, GROUP_CONCAT(value SEPARATOR ';') AS form 
            FROM coder_event_creator 
            WHERE variable = 'form'
            GROUP BY 1
        ) cec_form ON (cec.event_id = cec_form.event_id)
LEFT JOIN (SELECT 
            event_id, GROUP_CONCAT(value SEPARATOR ';') AS issue
            FROM coder_event_creator 
            WHERE variable = 'issue'
            GROUP BY 1
        ) cec_issue ON (cec.event_id = cec_issue.event_id)
LEFT JOIN (SELECT 
            event_id, GROUP_CONCAT(value SEPARATOR ';') AS racial_issue
            FROM coder_event_creator 
            WHERE variable = 'racial-issue'
            GROUP BY 1
        ) cec_racial_issue ON (cec.event_id = cec_racial_issue.event_id)        
"""

## get the query
df_long = pd.read_sql(query, con = mysql_engine)

## there should not be duplicates but here we are
df_long = df_long.drop_duplicates()

## remove skip users
df_long = df_long[~df_long['coder_id'].isin(skip_users)]

## get disqualified events and remove
disqualified_events = df_long[df_long['variable'].isin(disqualifying_variables)].event_id.unique()
df_long = df_long[~df_long['event_id'].isin(disqualified_events)]

## move text field into value if not null
df_long['value'] = df_long.apply(lambda x: x['text'] if x['text'] is not None else x['value'], axis = 1)

## pivot
columns = ['article-desc', 'desc', 'location', 'start-date'] 
df_int = df_long[df_long['variable'].isin(columns)]

df_int = df_int.drop_duplicates(['event_id', 'variable'])

df_int[['event_id', 'variable', 'value']].pivot(index = 'event_id', 
    columns = 'variable', values = 'value')

indexes = ['event_id', 'coder_id', 'article_id', 'publication', 'pub_date', 
    'title', 'form', 'issue', 'racial_issue']

## pivot on descs
df_wide1 = df_int.pivot(index = 'event_id', columns = 'variable', values = 'value')

## subset the stable columns
df_wide2 = df_long[indexes].drop_duplicates().set_index('event_id')

## join
df_wide = df_wide1.merge(df_wide2, left_index = True, right_index = True)

## rename a few things to be MySQL and SQLAlchemy friendly
df_wide = df_wide.rename(columns = {'article-desc': 'article_desc', 'start-date': 'start_date'})

df_wide = df_wide.reset_index()

## replace empty values with NaN
df_wide[df_wide == ''] = np.nan

## subset the relevant decision articles and remove from wide
df_wide_decisions = df_wide[df_wide.article_id.isin(df_decisions.article_id)]

## get the UR/PA articles
df_wide_urpa = df_wide[df_wide.article_id.isin(df_decisions.article_id) & \
    (df_wide.coder_id.str.startswith('UR_') | df_wide.coder_id.str.startswith('PA_'))]

## remove all other entries by article ID
df_wide = df_wide[~df_wide.article_id.isin(df_decisions.article_id)]

## inner join and readd into df_wide
## NB: there is a small delta here due to some of the decision'd articles being already
##     excluded as they contain disqualifying information.
df_wide = df_wide.append(df_wide_decisions.merge(df_decisions, on = ['article_id', 'event_id'], how = 'inner'))
df_wide = df_wide.append(df_wide_urpa)

## upload to MySQL
df_wide.to_sql(name = 'event_metadata',
            con = mysql_engine,
            if_exists= 'replace',
            index = True,
            index_label = 'id',
            dtype = {
                'id': sqlalchemy.types.Integer(),
                'coder_id': sqlalchemy.types.Text(),
                'event_id': sqlalchemy.types.Integer(),
                'article_id': sqlalchemy.types.Integer(),
                'article_desc': sqlalchemy.types.UnicodeText(),
                'desc': sqlalchemy.types.UnicodeText(),
                'location': sqlalchemy.types.Text(),
                'start_date': sqlalchemy.types.Date(),
                'publication': sqlalchemy.types.Text(),
                'pub_date': sqlalchemy.types.Date(),
                'title': sqlalchemy.types.Text(),
                'form': sqlalchemy.types.Text(),
                'issue': sqlalchemy.types.Text(),
                'racial_issue': sqlalchemy.types.Text()
            })
