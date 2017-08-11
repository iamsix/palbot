import requests
import csv

def get_presidential_approval(self, event):
    """
    Gets presidential approval ratings from fivethirtyeight
    
    :param event: IRC event
    :return: IRC event with output set
    """
    data_url = "https://projects.fivethirtyeight.com/trump-approval-data/approval_topline.csv"
    data = requests.get(data_url)

    data = data.content.decode('utf-8')
    data = data.splitlines()[0:4] # Only grab the top 3 lines from the CSV including the header

    reader = csv.DictReader(data)

    for row in reader:
        if row['subgroup'] == "All polls":
            break

    event.output = "President: {} Approval: {}% Disapproval: {}% Date: {} [ https://goo.gl/vva6Vy ]"
    event.output = event.output.format(row['president'], round(float(row['approve_estimate']), 1),
                                       round(float(row['disapprove_estimate']), 1), row['modeldate'])
    return event
    

get_presidential_approval.command = "!approval"
get_presidential_approval.helptext = get_presidential_approval.__doc__.splitlines()[0]

get_presidential_approval(None, get_presidential_approval)
print(get_presidential_approval.output)
