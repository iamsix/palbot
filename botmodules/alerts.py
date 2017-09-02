
def sub_alert(self, e):
    if e.input in [n.__name__ for n in self.botalerts]:
        if e.input in self.alertsubs:
            self.alertsubs[e.input].add(e.source.id)
        else:
            self.alertsubs[e.input] = set(e.source.id)
        #print( self.alertsubs[e.input])
        #prevent a blank item in the set
        self.alertsubs[e.input].discard("")
        self.botconfig['alerts'][e.input] = ",".join(self.alertsubs[e.input])
        with open('palbot.cfg', 'w') as configfile:
            self.botconfig.write(configfile)
        e.output = "{} has been subscribed to {}".format(e.source.name, e.input)
    else:
        e.output = "No such alert"
sub_alert.command = "!subscribe"

def unsub_alert(self, e):
    if e.input in self.alertsubs:
        #prevent a blank item in the set
        self.alertsubs[e.input].discard("")
        self.alertsubs[e.input].discard(e.source.id)
        e.output = "{} has been unsubscribed from {}".format(e.source.name, e.input)
        self.botconfig['alerts'][e.input] = ",".join(self.alertsubs[e.input])
        with open('palbot.cfg', 'w') as configfile:
            self.botconfig.write(configfile)
    else:
        e.output = "No such alert"
unsub_alert.command = "!unsubscribe"
