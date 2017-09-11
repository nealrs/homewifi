import requests
import os
from flask import Flask, request, session, redirect, render_template, Response, make_response, jsonify, url_for
from flask_ask import (
    Ask,
    request as ask_request,
    session as ask_session,
    context as ask_context,
    version, question, statement, audio, current_stream
)
from flask_sslify import SSLify
import logging
import urllib

from urlparse import urlparse
from peewee import *
from playhouse.db_url import connect
from playhouse.shortcuts import model_to_dict, dict_to_model

from datetime import datetime
from time import gmtime, strftime, mktime
import subprocess
from random import randint

app = Flask(__name__)
ask = Ask(app, '/')
sslify = SSLify(app)
app.secret_key = os.urandom(24)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
#logging.getLogger('flask_ask').setLevel(logging.DEBUG)

# Account for special characters!
charmap = {
    "~" : "tilde",
    "`" : "back tick",
    "!" : "exclamation point",
    "@" : "at sign",
    "#" : "hash tag",
    "$" : "dollar sign",
    "%" : "percent sign",
    "^" : "carret sign",
    "&" : "ampersand",
    "*" : "asterisk",
    "(" : "left parenthsis",
    ")" : "right parenthesis",
    "-" : "dash",
    "_" : "underscore",
    "+" : "plus sign",
    "=" : "equals sign",
    "{" : "left curly brace",
    "}" : "right curly brace",
    "[" : "left square bracket",
    "]" : "right square bracket",
    "|" : "vertical line",
    ":" : "colon",
    ";" : "semi colon",
    "\\" : "back slash",
    '"' : "double quotation mark",
    "'" : "apostrophe",
    "<" : "less than sign",
    "," : "comma",
    ">" : "greater than sign",
    "." : "period",
    "?" : "question mark",
    "/" : "forward slash"
}

#########################################################
# CONNECT TO REDIS & MYSQL + define ORM
sql = urlparse(os.environ['JAWSDB_URL'], "mysql")
db = MySQLDatabase(
    (sql[2])[1:],
    host=sql.hostname,
    user=sql.username,
    passwd=sql.password,
    port=int(sql.port)
)

# This hook ensures that a connection is opened to handle any queries generated by the request.
@app.before_request
def _db_connect():
    db.connect() # tertiary JawsDB (also RDS)
    logging.debug("mysql connect")

# This hook ensures that the connection is closed when we've finished processing the request.
@app.teardown_request
def _db_close(exc):
    if not db.is_closed():
        db.close()
        logging.debug("mysql close")

class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    userId = CharField(primary_key=True)
    signup = DateTimeField()
    ssid = TextField()
    wifi = TextField()


#########################################################
# DATABASE ACCESS METHODS
def db_get_user(userId):
    try:
        with db.atomic():
            user, created = User.get_or_create(
                userId=userId,
                defaults={
                    'signup': datetime.now() #datetime.strptime(datetime.now(), '%a, %d %b %Y %H:%M:%S -0400')
                }
            )
            return user
    except (IntegrityError, DoesNotExist) as e:
        logging.info("error retrieving user: "+str(userid)+" [db_get_user]")
        return None

def db_update_user(userId, ssid, wifi):
    try:
        with db.atomic():
            row = User.update(ssid=ssid, wifi=wifi).where(User.userId == userId).execute()
            return row
    except (IntegrityError, DoesNotExist) as e:
        logging.info("error updating user: "+str(userid)+" [db_update_user]")
        return None


def db_delete_user(userId):
    try:
        with db.atomic():
            deleted = User.delete().where(User.userId == userId).execute()
            return deleted
    except (IntegrityError, DoesNotExist) as e:
        logging.info("error deleting user: "+str(userid)+" [db_delete_user]")
        return None


# Helper Methods
def sessionInfo():
    logging.info("User ID: {}".format(ask_session.user.userId))
    #logging.info("Access token: {}".format(ask_session.user.accessToken))
    #logging.info("Device ID: {}".format(ask_context.System.device.deviceId))
    #logging.info("API endpoint: {}".format(ask_context.System.device.deviceId))
    #logging.info("Consent Token: {}".format(ask_context.System.apiEndpoint))
    #return str(ask_session.user.userId), str(ask_context.System.device.deviceId), str(ask_context.System.user.permissions.consentToken), str(ask_context.System.apiEndpoint)


def getUser(token):
    api = "https://api.amazon.com/user/profile?access_token="+str(token)
    r = requests.get(api)
    user = r.json()
    print user
    if r.status_code == 200:
        return user['name'], user['email'], user['user_id']
    else: 
        print "profile error"
        return None

def spellOut(term):
    mod = ""
    for t in term:
        if t.isupper():
            add = ("Capital " + t)
        elif t in charmap:
            add = charmap[t]
        else: 
            add = t
        mod = mod + add + ", "
    return mod


# FLASK ROUTES
@app.route("/", methods=["GET", "POST"])
def login():
    if 'userId' in session:
        return redirect(url_for("home", _scheme="https", _external=True))
    else:
        return render_template('login.html')

@app.route("/logout", methods=["GET", "POST"])
def logout():
    if 'userId' in session:
        session.clear()
    return redirect(url_for("login", _scheme="https", _external=True))


@app.route("/delete", methods=["GET", "POST"])
def delete():
    if 'userId' in session:
        deleted =  db_delete_user(session['userId'])
        print deleted
        if deleted > 0 :
            print "userId: "+ session['userId'] + " deleted successfully"
        else: 
            print "not able to delete userId: "+ session['userId']

        session.clear()
    return render_template('deleted.html')


@app.route("/handle_login_2/<token>/", methods=["GET", "POST"])
#@app.route('/app_response_token/', methods=['GET'])
def handle_login_2(token):
    #    return token
    #def handle_login():
    #print request.url
    #token = request.args.get('access_token')
    print "token: "
    print token
    logging.debug("token: "+str(token))

    name, email, userId  = getUser(token)
    session['name'] = name
    session['email'] = email
    session['userId'] = userId

    #if new user (check for amazon id) - create new record in db. If not, pull user info?
    user =  db_get_user(session['userId'])
    """print "**"
    print user.userId
    print user.signup
    print "**"
    """
    #return "ok! name: "+ name +" email: "+ email +", userId: "+ userId, 200
    return redirect(url_for("home", _scheme="https", _external=True))

@app.route("/handle_login", methods=["GET", "POST"])
def handle_login():
    return render_template('auth.html')
    
    
@app.route("/home", methods=["GET", "POST"])
def home():
    if 'userId' in session:
        user =  db_get_user(session['userId'])
    else: 
        return redirect(url_for("login", _scheme="https", _external=True))
    
    if 'updated' in session:
        updated = session['updated']
        session['updated'] = None
    else:
        updated = None
    """print "**"
    print user.userId
    print user.signup
    print user.ssid
    print user.wifi
    print "**"
    """

    ssid = user.ssid
    wifi = user.wifi
    return render_template('home.html', ssid=ssid, wifi=wifi, updated=updated)

@app.route("/update", methods=["GET", "POST"])
def update():
    user =  db_get_user(session['userId'])
    """print "\nuser info from database"
    print user.userId
    print user.signup
    print user.ssid
    print user.wifi"""

    #print "\nuser info from form"
    ssid = str(request.form['ssid'])
    wifi = str(request.form['wifi'])
    #print ssid
    #print wifi

    #print "\ndid database crap work?"
    if ssid != user.ssid or wifi != user.wifi:
        print "updating db!"
        result = db_update_user(user.userId, ssid, wifi)
        print result
        session['updated']=True
    else: 
        print "wifi/pass match, so no need to update db"
        session['updated']=None

    return redirect(url_for("home", _scheme="https", _external=True))

# Alexa Intents
@ask.launch
@ask.default_intent
@ask.intent('WifiIntent')
def launch():
    print "skill launch"
    sessionInfo()
    if ask_session.user.accessToken is None:
        speech = "Welcome to Home WiFi. Please open the Alexa app to link this Skill with your Amazon account."
        return statement(speech).link_account_card()
    else:
        name, email, userId  = getUser(ask_session.user.accessToken)
        user =  db_get_user(userId)
        
        """print "**"
        print user.userId
        print user.signup
        print user.ssid
        print user.wifi
        print "**"
        """

        ssid = user.ssid
        wifi = user.wifi
        
        if ssid != "" and wifi != "" and ssid is not None and wifi is not None:
            speech = "The wireless network name is "+spellOut(ssid)+", and the password is "+spellOut(wifi)
            card_title = "Get on the WiFi"
            card_text = "Network: "+ssid+"\nPassword: "+ wifi
            return statement(speech).simple_card(title=card_title, content=card_text)
        else:
            speech = "Please log in to Home Why Fi dot Heroku app dot com and update your why fi network name and password."
            card_title = "Setup your Home WiFi Account"
            card_text = "Go to https://homewifi.herokuapp.com/ to update your WiFi network name and password."
            return statement(speech).simple_card(title=card_title, content=card_text)
        
if __name__ == "__main__":
	app.run(debug=os.environ['DEBUG'])
