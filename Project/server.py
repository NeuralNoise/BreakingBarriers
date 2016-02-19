"""Text Translator."""

from jinja2 import StrictUndefined
import flask
from flask import Flask, render_template, request, flash, redirect, session, jsonify
from flask_debugtoolbar import DebugToolbarExtension
from model import connect_to_db, db, User, Language, Contact, Message, MessageLang, MessageContact
from sqlalchemy import distinct, func
import yandex, twilio_api
import json
from gevent import monkey; monkey.patch_all()
import datetime
from xml.etree import ElementTree
import gmail_contacts
import pickle
import gdata.contacts.client
import gmail_contacts




app = Flask(__name__)

# Required to use Flask sessions and the debug toolbar
app.secret_key = "ABC"

app.jinja_env.undefined = StrictUndefined


@app.route('/')
def index():
    """Homepage."""

    key = request.args.get("code")
    
    if key:
        user_id = flask.session['user_id']
        user = User.query.get(user_id)
        token = pickle.load(open('token' + str(user_id) + '.p', 'rb'))
        token.get_access_token(key)
        client = gdata.contacts.client.ContactsClient(source='appname')
        client = token.authorize(client)
        feed = client.GetContacts()
        contacts = gmail_contacts.parse_contacts(user, str(feed))

        return redirect("/users/%s" % user.user_id)

    else:
        
        return render_template("home.html")


@app.route('/register', methods=['GET'])
def register_form():
    """Show form for user signup."""

    language_list = Language.query.all()

    languages = []

    for lang in language_list:
        languages.append((lang.lang_id, lang.lang_name))
    
    return render_template("register_form.html", languages=languages)


@app.route('/register', methods=['POST'])
def register_process():
    """Process registration."""

    # Get form variables
    email = request.form.get("email")
    password = request.form.get("password")
    first_name = request.form.get("first_name")
    last_name = request.form.get("last_name")
    lang_id = request.form.get("lang_id")
    phone_number = request.form.get("phone")

    new_user = User(email=email, password=password, first_name=first_name,
                    last_name=last_name, lang_id=lang_id, phone_number=phone_number)

    db.session.add(new_user)
    db.session.commit()

    flash("User %s added." % email)
    return redirect("/login") 

@app.route('/login', methods=['GET'])
def login_form():
    """Show login form."""

    return render_template("login_form.html")


@app.route('/login', methods=['POST'])
def login_process():
    """Process login."""

    # Get form variables
    email = request.form.get("email")
    password = request.form.get("password")

    user = User.query.filter_by(email=email, password=password).first()

    if not user:
        flash("No such user")
        return redirect("/register")

    if user.password != password:
        flash("Incorrect password")
        return redirect("/login")

    session["user_id"] = user.user_id

    flash("Logged in")
    return redirect("/users/%s/send_text" % user.user_id)
#if there're no contacts, redirect to profile to add contacts

@app.route('/logout')
def logout():
    """Log out."""

    del session["user_id"]
    flash("Logged Out.")
    return redirect("/")

# USELESS
@app.route("/users")
def user_list():
    """Show list of users."""

    users = User.query.all()
    return render_template("user_list.html", users=users)


@app.route("/users/<int:user_id>", methods=["GET"])
def user_detail(user_id):
    """Show info about user."""
 
    user = User.query.get(user_id)
    user_contact_list = Contact.query.filter_by(user_id = user_id).all()

    contacts = []

    if len(user_contact_list) == 0:
        flash("The user has no contacts")
        return redirect("/users/%s/add_contact" % user_id)

    for contact in user_contact_list:
        contacts.append((contact.contact_phone, contact.language.lang_name, 
                         contact.contact_first_name))

    return render_template("user_profile.html", user=user, contacts=contacts, 
                            user_id=user_id)



    # TODO: create User controller that will handle user-related stuff
    # ex: vars = usercontroller.stuff(bla)

@app.route("/users/<int:user_id>/edit_user", methods=["GET"])
def show_user_edit(user_id):
    """Edit user's info."""

    return render_template("user_edit.html", user_id=user_id, first_name=first_name,
                            last_name=last_name, email= email, password=password)


@app.route("/users/<int:user_id>/edit_user", methods=["POST"])
def user_edit(user_id):
    """Edit user's info."""

    user = User.query.get(user_id)

    if user:
            user[0].first_name = first_name
            user[1].last_name = last_name
            user[2].email = email
            user[3].password = password
            user[4].lang_id = lang_id
            user[5].phone_number= phone_number

    db.session.commit()

    return redirect("/users/%s" % user_id)


@app.route("/users/<int:user_id>/add_contact", methods=['GET'])
def show_contact_form(user_id):
    """Show form for contact signup."""

    user = User.query.get(user_id)
    language_list = Language.query.all()

    languages = []

    for lang in language_list:
        languages.append((lang.lang_id, lang.lang_name))
    return render_template("contact_add.html", user_id=user_id, languages=languages)


@app.route("/users/<int:user_id>/add_contact", methods=["POST"])
def add_contact(user_id):
    """Add a contact."""

    first_name = request.form["first_name"]
    last_name = request.form["last_name"]
    language = request.form["lang_id"]
    phone = request.form["phone"]

    contact = Contact(contact_first_name=first_name, contact_last_name=last_name,
                    contact_phone=phone, user_id=user_id, lang_id=language)
    
    flash("Contact added.")
    db.session.add(contact)

    db.session.commit()

    return redirect("/users/%s" % user_id)


@app.route("/users/<int:user_id>/send_text", methods=["GET"])
def show_text_form(user_id):
    """Show send message form"""

    user_contact_list = Contact.query.filter_by(user_id = user_id).all()

    contacts = []

    if len(user_contact_list) == 0:
        flash("The user has no contacts, you need to add one")
        

    for contact in user_contact_list:
        contacts.append((contact.contact_phone, contact.language.lang_name, 
                         contact.contact_first_name))

    existing_message = ""

    return render_template("message_form.html", existing_message=existing_message, 
                            user_id=user_id, contacts=contacts)


@app.route("/users/<int:user_id>/send_text/submit", methods=["POST"])
def submit_text_form(user_id):
    """Send message"""

    user_message = request.form.get("text")

    user_id = session['user_id']
    user = User.query.filter_by(user_id=user_id).all()[0]
    original_lang_id = user.language.lang_id
    msg_sent_at = datetime.datetime.now()

    message = Message(message_text=user_message, user_id=user_id, 
                      original_lang_id=original_lang_id, message_sent_at=msg_sent_at)
    
    flash("Message added.")
    db.session.add(message)
    db.session.commit()

    contacts = user.contacts

    lang_code = user.language.yandex_lang_code
    trans_msgs = []
    contact_langs = []

    #making a unique list of contacts' langs
    for contact in contacts:
        contact_lang = contact.language.yandex_lang_code
        contact_langs.append(contact_lang)
    unique_list_lang = list(set(contact_langs))

    trans_msgs_dict = {}
    for unique_lang in unique_list_lang:
        contact_lang_id = contact.language.lang_id
        contact_msg_id = message.message_id
        trans_msg = yandex.translate_message(user_message, lang_code, contact_lang)['text']
        trans_status = yandex.translate_message(user_message, lang_code, contact_lang)['code']
        trans_msgs_dict[unique_lang] = trans_msg
        msg_lang = MessageLang(lang_id=contact_lang_id, message_id=contact_msg_id, translated_message=trans_msg,
                               message_status=trans_status)
        db.session.add(msg_lang)
    
    contact_dict = {}
    for contact in contacts:
        contact_lang = contact.language.yandex_lang_code
        contact_id = contact.contact_id
        contact_msg_id = message.message_id
        contact_dict[contact.contact_id] = trans_msgs_dict[contact_lang]
        msg = twilio_api.send_message(trans_msgs_dict[contact_lang], contact.contact_phone)
        msg_status = msg.status
        contact_msg = MessageContact(contact_id=contact_id, message_id=contact_msg_id, message_status=msg_status)
        db.session.add(contact_msg)    
    
    db.session.commit()
    flash('The translated texts have been sent')
    return redirect("/users/%s" % user_id)

# @app.route("/users/<int:user_id>/messages", methods=["GET"])
# def message_list(user_id):
#     """Show info about user's messages."""

#     messages = Message.query.all()
#     user_message = Message.query.filter_by(user_id=user_id).all()

#     return render_template("message_list.html", messages=messages)


@app.route("/users/<int:user_id>/send_text/preview", methods=["POST"])
def preview_message(user_id):
    """Preview translated message"""

    user_message = request.form.get("text")

    print user_message
    if user_message:
        user_id = session['user_id']
        user = User.query.filter_by(user_id=user_id).all()[0]

        contacts = user.contacts

        lang_code = user.language.yandex_lang_code
        trans_msgs = []

        for contact in contacts:
            contact_lang = contact.language.yandex_lang_code
            if lang_code == contact_lang:
                trans_msgs.append([user_message])
            else:
                trans_msg = yandex.translate_message(user_message, lang_code, contact_lang)['text']
                trans_msgs.append(trans_msg)

    return json.dumps(trans_msgs)

    # TODO: create Language controller that will have all above stuff, 
    # calling translate_message() function from that controller in this route 

@app.route("/", methods=["POST", "GET"])
def send_text():
    """Receive text via Twilio"""
    
    contact_phone = request.values.get("From", None)
    response_message = request.values.get("Body", None)

    message_status = request.values.get("SmsStatus", None)


    if contact_phone != None:
        contact_phone = contact_phone[2:]
        contacts = Contact.query.filter_by(contact_phone=contact_phone).all()
        contact_id_list = []

        for contact in contacts:
            contact_id_list.append(contact.contact_id)
        msg_id = db.session.query(func.max(MessageContact.message_id)).filter(MessageContact.contact_id.in_(contact_id_list)).one()
        msg = Message.query.filter_by(message_id=msg_id).one()
        user = msg.user
        user_phone = user.phone_number
        to_lang = user.language.yandex_lang_code
        # all contacts that belong to that user and get a first one that matches the phone number
        from_contact = Contact.query.filter((Contact.user_id==user.user_id) & (Contact.contact_phone==contact_phone)).first()
        from_lang = from_contact.language.yandex_lang_code
        translated_resp_msg = yandex.translate_message(response_message, from_lang, to_lang)
        twilio_api.send_message(translated_resp_msg, user_phone)

        return ('', 204)

    else:
        render_template('home.html')

#TODO send text & preview buttons which will return AJAX response with diff routes

@app.route("/users/<int:user_id>/contacts", methods=["POST", "GET"])
def redirect_gmail(user_id):
    """Redirect the user to gmail access page"""

    authorized_url = gmail_contacts.authorize_url(flask.session, user_id)

    return json.dumps(authorized_url)


if __name__ == "__main__":
    # We have to set debug=True here, since it has to be True at the point
    # that we invoke the DebugToolbarExtension

    # Do not debug for demo
    app.debug = True

    app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False

    connect_to_db(app)

    # Use the DebugToolbar
    DebugToolbarExtension(app)

    app.run()
