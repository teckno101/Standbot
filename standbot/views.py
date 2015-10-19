from django.views.generic.base import View
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
import requests, json
import random
from models import Meeting

class SlackEndpoint (View):
    @csrf_exempt #allow any website, not just ones in our domain, to access the endpoint
    def dispatch(self, request, *args, **kwargs):
        return super(SlackEndpoint, self).dispatch(request, *args, **kwargs)

    def post(self, request):
        incomingSlackData = request.POST.dict()
        import slackbot_settings

        if incomingSlackData['token'] != slackbot_settings.incoming_slack_token_from_outgoing_webhook:
            return JsonResponse({'error': 'not authorized'})
        elif incomingSlackData['user_name'] == 'slackbot':
            return HttpResponse()
        else:
            try:
                meetingDB = Meeting.objects.get(channel='C0CMUCBBM')
                meetingInProgress=True
            except:
                meetingInProgress=False
                meetingDB = None
                # dataToReturn = {"text": "Meeting not in progress. Respond with 'start' to start a new one."}
                # return JsonResponse(dataToReturn)

            if incomingSlackData['text']=='start':
                return self.startCommand(meetingDB, meetingInProgress,
                                        slackbot_settings.usernames, slackbot_settings.shuffle)

            if incomingSlackData['text']=='quit':
                return self.quitCommand(meetingDB, meetingInProgress)

            if meetingInProgress and incomingSlackData['text']=='ready':
                return self.readyCommand(meetingDB, incomingSlackData)

            if meetingInProgress and incomingSlackData['text']=='skip':
                return self.skipCommand(meetingDB)

            if meetingInProgress and incomingSlackData['text']=='dismiss':
                return self.dismissCommand(meetingDB)


            if meetingInProgress and incomingSlackData['text'][0:6]!='ignore' \
                    and "@"+incomingSlackData['user_name']==meetingDB.currentMember:
                return self.questionAnswer(meetingDB)

        return HttpResponse()

    def sendSlackMessage(self, message):
        import slackbot_settings
        incomingWebHookURL = slackbot_settings.incoming_slack_webhook_url

        payload = {
            "text": message,
            "username": "standbot",
            # "channel": "#standup",
            "link_names": 1
        }

        r = requests.post(incomingWebHookURL, json.dumps(payload), headers={'content-type': 'application/json'})

    def startCommand(self, meetingDB, meetingInProgress, usernames, shuffle):
        if meetingInProgress:
            self.sendSlackMessage("Meeting already in progress")
            return HttpResponse()

        if shuffle:
            random.shuffle(usernames)

        meetingDB = Meeting(channel='C0CMUCBBM',
                            meetingOrder=json.dumps(usernames),
                            questionNum=1,
                            currentMember=usernames[0])
        meetingDB.save()

        self.sendSlackMessage("Let's get this meeting started! The order today will be: " + ", ".join(usernames))
        self.sendSlackMessage("What did you do since your last standup?")
        return HttpResponse()

    def quitCommand(self, meetingDB, meetingInProgress):
        if meetingInProgress:
            meetingDB.delete()
            self.sendSlackMessage("Meeting closed")
        else:
            self.sendSlackMessage("No meeting in progress")
        return HttpResponse()


    def readyCommand(self, meetingDB, incomingSlackData):
        meetingOrderAsList = json.loads(meetingDB.meetingOrder)
        currentMemberIndex = meetingOrderAsList.index(meetingDB.currentMember)

        self.sendSlackMessage("Ok @"+incomingSlackData['user_name']+' wants to go. We\'ll come back to ' \
                         + meetingDB.currentMember)

        meetingOrderAsList.remove('@'+incomingSlackData['user_name'])
        meetingOrderAsList.insert(currentMemberIndex, '@'+incomingSlackData['user_name'])
        meetingDB.meetingOrder = json.dumps(meetingOrderAsList)
        meetingDB.currentMember = '@'+incomingSlackData['user_name']
        meetingDB.questionNum=1

        meetingDB.save()

        return JsonResponse({"text": "What did you do since your last standup?"})

    def skipCommand(self, meetingDB):
        currentMemberIndex = json.loads(meetingDB.meetingOrder).index(meetingDB.currentMember)
        try:
            nextUsername = json.loads(meetingDB.meetingOrder)[currentMemberIndex+1]
        except:
            nextUsername = json.loads(meetingDB.meetingOrder)[currentMemberIndex]

        self.sendSlackMessage("Ok, we'll skip " + meetingDB.currentMember+". "+ nextUsername + " you're up")

        userToAddToEnd = meetingDB.currentMember
        meetingDB.currentMember = nextUsername
        meetingOrderAsList = json.loads(meetingDB.meetingOrder)
        meetingOrderAsList.remove(userToAddToEnd)
        meetingOrderAsList.append(userToAddToEnd)
        meetingDB.meetingOrder = json.dumps(meetingOrderAsList)

        meetingDB.save()
        return HttpResponse()

    def dismissCommand(self, meetingDB):
        currentMemberIndex = json.loads(meetingDB.meetingOrder).index(meetingDB.currentMember)
        if currentMemberIndex == len(json.loads(meetingDB.meetingOrder))-1:
            meetingDB.delete()
            return JsonResponse({"text": "Standup for today is complete. Thanks!"})

        nextUsername = json.loads(meetingDB.meetingOrder)[currentMemberIndex+1]

        self.sendSlackMessage("Ok " + meetingDB.currentMember+" is out for today. "+ nextUsername + " you're up")

        userToAddToBeginning = meetingDB.currentMember
        meetingDB.currentMember = nextUsername

        meetingOrderAsList = json.loads(meetingDB.meetingOrder)
        meetingOrderAsList.remove(userToAddToBeginning)
        meetingOrderAsList.insert(0, userToAddToBeginning)
        meetingDB.meetingOrder = json.dumps(meetingOrderAsList)

        meetingDB.save()
        return HttpResponse()

    def questionAnswer(self, meetingDB):
        if meetingDB.questionNum == 0:
            meetingDB.questionNum = 1
            meetingDB.save()
            return JsonResponse({"text": "What did you do since your last standup?"})
        if meetingDB.questionNum == 1:
            meetingDB.questionNum = 2
            meetingDB.save()
            return JsonResponse({"text": "What are you doing today?"})
        elif meetingDB.questionNum == 2:
            meetingDB.questionNum = 3
            meetingDB.save()
            return JsonResponse({"text": "Do you have any roadblocks?"})
        elif meetingDB.questionNum == 3:
            currentMemberIndex = json.loads(meetingDB.meetingOrder).index(meetingDB.currentMember)
            if currentMemberIndex == len(json.loads(meetingDB.meetingOrder))-1:
                meetingDB.delete()
                self.sendSlackMessage("Standup for today is complete. Thanks!")
                r = requests.get("http://fortunecookieapi.com/v1/cookie")
                self.sendSlackMessage("Your fortune cookie message is: \"" + r.json[0]['fortune']['message'])+"\""
                return HttpResponse()

            nextUsername = json.loads(meetingDB.meetingOrder)[currentMemberIndex+1]

            self.sendSlackMessage("Thanks " + meetingDB.currentMember+". "+ nextUsername + " you're up")

            meetingDB.questionNum = 1
            meetingDB.currentMember = nextUsername
            meetingDB.save()

            return JsonResponse({"text": "What did you do since your last standup?"})
        else:
            return HttpResponse()