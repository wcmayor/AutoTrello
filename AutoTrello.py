from trello import TrelloClient
from datetime import datetime
from pytz import timezone
import re
import os
import boto3
import json

def AutoTrello(event, context):
    
    #vars for getting the api connection info from secrets manager
    secrets_region = os.getenv('SECRETS_REGION')
    secret_name = os.getenv('TRELLO_SECRET_NAME')
    api_key_name = os.getenv('TRELLO_API_KEY_NAME')
    api_token_name = os.getenv('TRELLO_API_TOKEN_NAME')

    #connect to secrets manager
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=secrets_region)

    #load the secret
    secrets = json.loads(client.get_secret_value(SecretId=secret_name)["SecretString"])

    #loop through the items in the secret, find the things we want
    for key, value in secrets.items():
        if key == api_key_name:
            api_key = value[:]
        if key == api_token_name:
            api_token = value[:]

    #timezone vars
    use_timezone = os.getenv('TRELLO_TIMEZONE')
    todaysdate = datetime.now(timezone(use_timezone)).date()

    client = TrelloClient(api_key=api_key, token=api_token)

    boards = client.list_boards()

    for board in boards:
        autotrello_list = board.list_lists(list_filter="'name':'AutoTrello'")
        for list in autotrello_list:
            for card in list.list_cards():
                settings_card = False
                for label in card.labels:
                    if label.name == "Settings":
                        print("Found settings card '" + card.name + "'")
                        settings_card = True
        lists = board.list_lists()
        print("Looking for lists that match our desired names on board '" + board.name + "'")
        for l in lists:
            if l.name == 'AutoTrello':
                print("Found list 'AutoTrello'")
                cards = l.list_cards()
                for card in cards:
                    repeatinterval = None
                    destlist = None
                    repostcard = False
                    duplicatecard = False
                    for label in card.labels:
                        label = label.name
                        results = re.search(r'Repeat: (every )?([0-9]+) days?', str(label))
                        if results:
                            if int(results.group(2)) > 0:
                                repeatinterval = int(results.group(2))
                        if label == "Repeat: monthly":
                            repeatinterval = 'monthly'
                        results = re.search(r'Board: (.*)', str(label))
                        if results:
                            for innerlist in lists:
                                if innerlist.name == results.group(1):
                                    for innercard in innerlist.list_cards():
                                        innercardname = innercard.name
                                        if innercardname == card.name:
                                            duplicatecard = True
                                    destlist = results.group(1)
                    if repeatinterval and destlist:
                        duedatedate = card.due_date.astimezone(timezone(use_timezone)).date()
                        if isinstance(repeatinterval, int):
                            datediff = (todaysdate - duedatedate).days
                            if datediff % repeatinterval == 0:
                                repostcard = True
                        elif repeatinterval == 'monthly':
                            if todaysdate.day == duedatedate.day:
                                repostcard = True
                    if repostcard:
                        newduedate = card.due_date.astimezone(timezone(use_timezone))
                        newduedate = newduedate.replace(year=todaysdate.year)
                        newduedate = newduedate.replace(month=todaysdate.month)
                        newduedate = newduedate.replace(day=todaysdate.day)
                        newduedate = newduedate.astimezone(timezone('UTC'))
                        for innerlist in lists:
                            if innerlist.name == destlist:
                                if not duplicatecard:
                                    newcard = innerlist.add_card(name=card.name, due=str(newduedate))
                                    for newmember in card.idMembers:
                                        newcard.assign(newmember)
                                else:
                                    for innercard in innerlist.list_cards():
                                        innercardname = innercard.name
                                        if innercardname == card.name:
                                            innercard.comment('AutoTrello: updating due date from ' + str(innercard.due_date.astimezone(timezone(use_timezone))) + ' to ' + str(newduedate.astimezone(timezone(use_timezone))))
                                            innercard.set_due(due=newduedate.astimezone(timezone(use_timezone)))
            elif l.name == "Done!":
                print("Found 'Done!' list, checking for cards not marked complete")
                cards = l.list_cards()
                for card in cards:
                    if not card.is_due_complete:
                        print("Found card '" + card.name + "' that is not complete, marking complete.")
                        card.set_due_complete()
                        card.comment("AutoTrello: Setting due as completed, as this card is on the 'Done!' list")

if __name__ == "__main__":
    AutoTrello(None, None)

    