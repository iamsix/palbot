# things like decode html entities, pretty time deltas, ordinals, etc

class Datamassagers:
    ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])

# html.unescape()

# pretty time delta
