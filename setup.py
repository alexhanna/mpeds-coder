from database import db_session, init_db
from models import User, ArticleMetadata, CodeFirstPass, CodeSecondPass, CodeEventCreator, \
	ArticleQueue, SecondPassQueue, EventCreatorQueue, Event
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

import csv
import random
import glob
import json

import config

def addArticlesExample(db_name = 'test'):
	""" Add articles from example directory. """

	print("Adding example articles...")
	articles = []
	for f in glob.iglob(config.DOC_ROOT + "*.txt"):
		print(f)
		filename = f.split('/')[-1]
		lines    = open(f, 'r').read().split("\n")
		title    = lines[0].replace("TITLE: ", "")

		articles.append( ArticleMetadata(filename = filename, title = title, db_name = db_name) )

	db_session.add_all(articles)
	db_session.commit()


def addArticles(filename, db_name):
	articles = []
	with open(filename, "rb") as csvfile:
		reader = csv.DictReader(csvfile)
		for row in reader:
			row = {k:v.decode("utf8") for k, v in row.items()}
			title = row['title']
			db_id = row['db_id']
			pub_date = row['pub_date']
			publication = row['publication']
			source_description = row.get('source_description')
			text = row['text']
			try:
				db_session.add(
					ArticleMetadata(
						title = title,
						db_name = db_name,
						db_id = db_id,
						filename = db_id,
						pub_date = pub_date,
						publication = publication,
						source_description = source_description,
						text = text)
					)
				db_session.commit()
			except IntegrityError as detail:
				print(detail)
				db_session.rollback()
				continue


def addUsersExample():
	""" Add some example users. """
	print("Adding example users...")

	## Add admin
	db_session.add(User(username = 'admin', password = 'default', authlevel = 3))

	## add first pass coders
	db_session.add(User(username = 'coder1p_1', password = 'default', authlevel = 1))
	db_session.add(User(username = 'coder1p_2', password = 'default', authlevel = 1))

	## second pass coders
	db_session.add(User(username = 'coder2p_1', password = 'default', authlevel = 2))
	db_session.add(User(username = 'coder2p_2', password = 'default', authlevel = 2))

	db_session.commit()


def addQueueExample():
	print("Adding example queues...")

	articles = db_session.query(ArticleMetadata).all()
	random.shuffle(articles)

	users = db_session.query(User).filter(User.authlevel == 1).all()

	aq  = []
	ecq = []
	## assign articles randomly to core team members for funsies
	for a in articles:
		for u in users:
			aq.append( ArticleQueue(article_id = a.id, coder_id = u.id) )
			ecq.append( EventCreatorQueue(article_id = a.id, coder_id = u.id) ) 

	db_session.add_all(aq)
	db_session.add_all(ecq)
	db_session.commit()


def main():
	init_db()

if __name__ == '__main__':
	main()
