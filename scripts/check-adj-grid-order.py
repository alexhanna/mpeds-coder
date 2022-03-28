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

adj_grid_order = []
if os.path.isfile('../adj-grid-order.yaml'):
    adj_load = yaml.load(open('../adj-grid-order.yaml', 'r'), 
        Loader = yaml.Loader)

    for x in adj_load:
        k,v = list(x.items())[0]
        adj_grid_order.append( k )

with mysql_engine.connect() as connection:
    for k in adj_grid_order:
        result = connection.execute("SELECT COUNT(*) as c FROM coder_event_creator WHERE variable = '{}'".format(k))
        for row in result:
            print(k, ':', row['c'])