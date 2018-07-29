# in which I implement a super-simple oauth interface just to read a publically available feed
import json
import urllib, urllib.request, urllib.parse
import datetime
import base64


def __init__(self):
  
  try:
    auth = "%s:%s" % (self.botconfig["APIkeys"]["twitterConsumerKey"], self.botconfig["APIkeys"]["twitterConsumerSecret"])
    auth = "Basic ".encode() + base64.b64encode(auth.encode())

    body = "grant_type=client_credentials".encode()
    headers = {"Authorization": auth, "Content-Type" : "application/x-www-form-urlencoded;charset=UTF-8"}
    url = "https://api.twitter.com/oauth2/token"
    req = urllib.request.Request(url, body, headers)
    response = urllib.request.urlopen(req)
    response = json.loads(response.read().decode('utf-8'))
    read_timeline.holyshitbearstoken = response['access_token']
    read_timeline.self = self
  except Exception as inst:
     self.logger.debug(inst)

def read_timeline (user):
    url = "https://api.twitter.com/1.1/statuses/user_timeline.json?screen_name=%s&count=1&tweet_mode=extended" % user
    opener = urllib.request.build_opener()
    opener.addheaders = [('Authorization', 'Bearer ' + read_timeline.holyshitbearstoken)]
    response = opener.open(url).read().decode('utf-8')
    tweet = json.loads(response)
    updated = datetime.datetime.strptime(tweet[0]['created_at'], "%a %b %d %H:%M:%S +0000 %Y")
    ago = round((datetime.datetime.utcnow() - updated).seconds/60)
    text = tweet[0]['user']['screen_name'] + ": " + tweet[0]['full_text']
    try:
      text = read_timeline.self.tools['decode_htmlentities'](text)
    except:
      pass
    return text, updated, ago

def latest_breaking(self, e):
    text, updated, ago = read_timeline('realdonaldtrump')
    e.output =  "%s (%s minutes ago) " % (text, ago)
    return e
latest_breaking.command = "!trump"
latest_breaking.helptext = "Usage: !breaking\nShows the latest breaking news alert"

def latest_tweet(self, e):
    text, updated, ago = read_timeline(e.input)
    e.output =  "%s (%s minutes ago) " % (text, ago)
    return e
latest_tweet.command = "!lasttweet"

def trump_alert(self):
    #returns a new breaking news only if it hasn't returned it before
      try:
        description, updated, ago = read_timeline('realdonaldtrump')

        if not trump_alert.lastcheck:
            self.logger.debug("First run empty, setting lastcheck to {}".format(updated))
            trump_alert.lastcheck = updated
        if updated > trump_alert.lastcheck:
            self.logger.debug("should be doing a tweet now")
            trump_alert.lastcheck = updated
            return description
      except Exception as inst:
          self.logger.exception(str(inst))
          pass
trump_alert.lastcheck = ""
trump_alert.alert = True
