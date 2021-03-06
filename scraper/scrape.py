import os
from collections import OrderedDict
import time
import argparse
import re
import csv
import json
import sys
from getpass import getpass
import pickle

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
from pymongo import MongoClient


# Helper function definitions
def check_exists_by_xpath(xpath, driver):
    try:
        driver.find_element_by_xpath(xpath)
    except NoSuchElementException:
        return False
    return True

def check_exists_by_css_selector(selector, driver):
    try:
        driver.find_element_by_css_selector(selector)
    except NoSuchElementException:
        return False
    return True


# Login function
def login_to_tigernet_with_driver(driver, load_cookies):
    driver.get('https://secure.tigernet.princeton.edu/s/1760/02-tigernet/index.aspx?sid=1760&gid=2&pgid=3&cid=40&returnurl=http%3a%2f%2ftigernet.princeton.edu%2fs%2f1760%2f02-tigernet%2findex.aspx%3fgid%3d2%26pgid%3d254')

    # load login cookies from previous sessions
    if load_cookies:
        cookies = pickle.load(open("cookies.pkl", "rb"))
        for cookie in cookies:
            driver.add_cookie(cookie)
    else:
        print('Cookies not loaded - if not first run, run with --load_cookies to login faster.')


    # Click on login
    driver.find_element_by_id('cid_40_rptSsoProviders_ctl02_btnProvider').click()
    print('Attempting to log in')

    # if we logged in successfully with cookies we shouldn't
    # see a login link - check edge cases here, sometimes it was
    # correct to check for a username field but it was slower
    # because it waited until finished.
    cookies_succeded = False
    if load_cookies:
        cookies_succeded = check_exists_by_css_selector(
                '#imodcmscalendar1016 > table > tbody > tr:nth-child(2) > td > div > div > div:nth-child(2) > div.thumb > a',
                driver
            )

    if not cookies_succeded:
        # Only print failed to load cookies if we actually tried
        if load_cookies:
            print('Failed to load cookies; logging in manually.')

        # Fill out fields and log in
        username = driver.find_element_by_id('username')
        password = driver.find_element_by_id('password')
        try:
            username.send_keys(os.getenv('USERNAME'))
            password.send_keys(os.getenv('PASSWORD'))
        except:
            print('Username and password environment variables not found; please enter your username and password.\n(don\'t worry, these are not saved).')
            username.send_keys(sanitized_input('Username: '))
            password.send_keys(getpass('Password: '))
            print('Attempting to log in')


        driver.find_element_by_name('submit').click()

        # see if duo-authentication is visible
        duo_visible = check_exists_by_css_selector(
            '#duo_iframe',
            driver
            )
        if duo_visible:
            print('Duo authentication iframe visible')
            driver.switch_to_frame('duo_iframe')

            print('Clicking \'Remember me for 90 days\' checkbox')
            driver.find_element_by_xpath('//*[@id="login-form"]/div/div/label/input').click()

            print('Duo authentication required; how would you like to proceed?\nOptions: (\'push\') [TODO (not implemented): \'call\', \'passcode\']')

            duo_method = sanitized_input(': ')
            while duo_method not in ['push']: #, 'call', 'passcode']
                print('Please choose one of the available authentication options:\n(\'push\') [TODO (not implemented): \'call\', \'passcode\']')
                duo_method = sanitized_input(': ')
            if duo_method == 'push':
                push_button = driver.find_element_by_css_selector('#login-form > fieldset:nth-child(10) > div.row-label.push-label > button')
                push_button.click()
            elif duo_method == 'call':
                raise ValueError(duo_method + ' not yet implemented.')
            elif duo_method == 'passcode':
                raise ValueError(duo_method + ' not yet implemented.')
            else:
                raise ValueError('Somehow an invalid value for duo_method made it past sanitized user input; please debug.')


        # see if we can see the link to the alumni search page
        # which would mean we logged in successfully.
        link_visible = check_exists_by_css_selector(
            '#imodcmscalendar1016 > table > tbody > tr:nth-child(2) > td > div > div > div:nth-child(2) > div.thumb > a',
            driver
            )
        if link_visible:
            print('Saving Login Cookies')
            pickle.dump( driver.get_cookies() , open("cookies.pkl","wb"))
        else:
            raise Exception(
                'Could not log in - please try a different driver type (e.g. chrome) to diagnose'
                )


# Scrape by index
def scrape_from_index_with_driver_with_database(driver, database):
    response = input('What index should we start scraping tigernet from? (1 - 184096): ')
    # While response has non-alphanumeric characters
    # see https://docs.python.org/2/howto/regex.html
    while re.search('[\D]', response) or 1 <= int(response.strip()) <= 184096:
        print("ERROR: Illegal query - please choose a starting index from 1 to 184096.")

        # ask again since incorrect
        response = input('Starting index (1 - 184096): ')

    response2 = input('How many values should we scrape from tigernet? (1 - 50): ')
    # While response has non-alphanumeric characters
    # see https://docs.python.org/2/howto/regex.html
    while re.search('[\D]', response2) or 1 > int(response2.strip()) > 50 or int(response.strip()) + int(response2.strip()) > 184096:
        print("ERROR: Illegal query - please choose an integer from 1 to 50, Tiger Net rate limits to 50 queries per day.")

        # ask again since incorrect
        response2 = input('Values to scrape (1 - 50): ')

    scrape_n_from_index_with_driver_with_database(int(response2.strip()), int(response.strip()), driver, database)

def scrape_n_from_index_with_driver_with_database(n_alumns, start_index, driver, database):
    # n_alumns in total = 184096
    print('Setting Up Environment to Scrape '
        + str(n_alumns)
        + ' from index '
        + str(start_index)
        )
    end_index = start_index + n_alumns + 1 # 1 longer because range is not inclusive

    speed = 0
    alpha = 0.1 # moving average scaling factor for time estimate

    print('Start Scraping Loop')

    for i in range(start_index, end_index):
        print('Loading Page with id: ' + str(i))
        start_time = time.time()

        # Load alumnus page and save to database
        get_alumnus_at_index_with_driver_with_database(i, driver, database)

        elapsed_time = time.time() - start_time
        if i == start_index:
            speed = elapsed_time
        else:
            speed = (speed * (1 - alpha)) + (elapsed_time * alpha)
        etc = speed * end_index - i
        print('Time Elapsed: %.2f' % elapsed_time + ' Current Speed: %.2f' % speed + ' Estimated Time to Completion: %.2f' % etc)

    print('Updated Mongo with ' + str(n_alumns) + ' Scraped Values')

def alumnus_url_with_index(index):
    return 'http://tigernet.princeton.edu/s/1760/02-tigernet/index.aspx?sid=1760&gid=2&pgid=275&cid=735&mid=' + str(index) + '#/PersonalProfile'


# Scrape from queue
def scrape_from_queue_with_driver_with_database(driver, database):
    response = input('How many values should we scrape from the alumni link queue? (1 - 50): ')
    # While response has non-alphanumeric characters
    # see https://docs.python.org/2/howto/regex.html
    while re.search('[\D]', response) or 1 > int(response.strip()) > 50:
        print("ERROR: Illegal query - please use an integer from 1 to 50, Tiger Net rate limits to 50 queries per day.")

        # ask again since incorrect
        response = input('Values to scrape (1 - 50): ')

    scrape_n_from_queue_with_driver_with_database(int(response.strip()), driver, database)

def scrape_n_from_queue_with_driver_with_database(n_alumns, driver, database):
    # n_alumns in total = 184096
    print('Setting Up Environment to Scrape '
        + str(n_alumns)
        + ' from queue'
        )
    end_index = n_alumns + 1 # 1 longer because range is not inclusive

    speed = 0
    alpha = 0.1 # moving average scaling factor for time estimate

    print('Start Scraping Loop')

    with open('alumni_page_queue.csv', 'r') as csvfile, open('alumni_page_queue_TEMP.csv', 'w') as out:
        reader = csv.reader(csvfile)
        writer = csv.writer(out)
        for i,row in enumerate(reader):
            if 0 <= i < end_index:
                alumnus_index = row[0]

                start_time = time.time()

                # Load alumnus page and save to database
                get_alumnus_at_index_with_driver_with_database(alumnus_index, driver, database)

                elapsed_time = time.time() - start_time
                if i == 0:
                    speed = elapsed_time
                else:
                    speed = (speed * (1 - alpha)) + (elapsed_time * alpha)
                etc = speed * end_index - i
                print('Time Elapsed: %.2f' % elapsed_time + ' Current Speed: %.2f' % speed + ' Estimated Time to Completion: %.2f' % etc)
            else:
                # delete already scraped rows
                writer.writerow(row)

    os.rename('alumni_page_queue_TEMP.csv', 'alumni_page_queue.csv')

    print('Updated Mongo with ' + str(n_alumns) + ' Scraped Values')


# Loads page with index and saves information to mongo instance
def get_alumnus_at_index_with_driver_with_database(alumnus_index, driver, database):
    if database.find({'_id' : str(alumnus_index)}).limit(1).count(with_limit_and_skip = True) > 0:
        print('Alumnus with index ' + alumnus_index + ' already exists in database. Skipping.')
        return

    print('Loading Page with id: ' + str(alumnus_index))
    driver.get(alumnus_url_with_index(alumnus_index))

    alumni_data = {}

    # My Information Loop
    # Since the fields all change but the paths don't, get all the fields
    # and label them accordingly.

    print('Getting Keys')
    keys = driver.find_elements_by_xpath('//*[@id="imod-view-content"]/div/div/div/div[2]/div/div[2]/ul/li/div[1]')

    print('Getting Values')
    values = driver.find_elements_by_xpath('//*[@id="imod-view-content"]/div/div/div/div[2]/div/div[2]/ul/li/div[2]')

    for key, value in zip(keys, values):
        alumni_data[key.get_attribute('innerHTML').rstrip(':')] = value.get_attribute('innerHTML')

    print('Updating Mongo with id: ' + str(alumnus_index))
    database.update({ '_id': str(alumnus_index) }, { '$set': alumni_data }, upsert = True)
    print(str(alumnus_index) + ': ' + values[2].get_attribute('innerHTML'))


# Scrape by search query
def scrape_by_query_with_driver(driver):
    print('Scraping by query')
    alumni_search_link = driver.find_element_by_css_selector(
        '#imodcmscalendar1016 > table > tbody > tr:nth-child(2) > td > div > div > div:nth-child(2) > div.thumb > a'
    )
    alumni_search_link.click()
    # Might need to click on advanced search here

    # Get input fields
    inputFields = OrderedDict()
    inputFields['first_name'] = driver.find_element_by_id('mf_405')
    inputFields['last_name'] = driver.find_element_by_id('mf_406')
    inputFields['city'] = driver.find_element_by_id('mf_85')
    inputFields['zip'] = driver.find_element_by_id('mf_87')
    inputFields['job_title'] = driver.find_element_by_id('mf_231')
    inputFields['employer'] = driver.find_element_by_id('mf_233')

    # Get select fields separately
    selectFields = OrderedDict()
    selectFields['year'] = Select(driver.find_element_by_id('mf_882'))
    selectFields['degree'] = Select(driver.find_element_by_id('mf_408'))
    selectFields['grad'] = Select(driver.find_element_by_id('mf_881'))
    selectFields['major'] = Select(driver.find_element_by_id('mf_409'))
    selectFields['cert'] = Select(driver.find_element_by_id('mf_410'))
    selectFields['activity'] = Select(driver.find_element_by_id('mf_411'))
    selectFields['state'] = Select(driver.find_element_by_id('mf_1003'))
    selectFields['country'] = Select(driver.find_element_by_id('mf_1004'))
    selectFields['paa'] = Select(driver.find_element_by_id('mf_254'))
    selectFields['field'] = Select(driver.find_element_by_id('mf_412'))
    selectFields['connect'] = Select(driver.find_element_by_id('mf_880'))
    selectFields['willing_to'] = Select(driver.find_element_by_id('mf_878'))

    print('You can query by any combination (one at a time) of the following keys: ')
    for key in inputFields.keys():
        print(key)
    for key in selectFields.keys():
        print(key)



    query = sanitized_input('Please enter your search KEY (e.g. \'employer\'): ')
    while not query in inputFields.keys() and not query in selectFields.keys() and query != 'done':
        print('ERROR: Please choose a search key from the above list of options. If finished, please type \'done\'.')
        query = sanitized_input('KEY (e.g. \'employer\'): ')

    # query is one from the list.
    field = None
    select_flag = False
    if query in inputFields.keys():
        field = inputFields[query]
    else:
        field = selectFields[query]
        # Set select_flag to true because we need to treat the field
        # as a Select() object
        select_flag = True

    query_value = sanitized_input('What value would you like to search for?: ')
    if not select_flag:
        field.send_keys(query_value)
    else:
        selector_visible = check_exists_by_xpath(
            "//option[contains(text(),'%s')]" % query_value,
            driver
        )
        while not selector_visible and query_value != 'done':
            print('ERROR: Query option not found in ' + query + '. Please choose another.')
            query = sanitized_input('Query (e.g. for class year, \'1986\'): ')
            selector_visible = check_exists_by_xpath(
                "//option[contains(text(),'%s')]" % query_value,
                driver
            )

        field_value = driver.find_element_by_xpath("//option[contains(text(),'%s')]" % query_value)
        field_value.click()

    search_button = driver.find_element_by_css_selector('#imod-view-content > section > div.imod-search-form.imod-field-label-align-left > div.imod-button-section > button')
    search_button.click()

    get_alumni_search_result_links_with_driver_with_query(driver, query + ': ' + query_value)

def sanitized_input(msg):
    response = input(msg)
    # While response has non-alphanumeric characters
    # see https://docs.python.org/2/howto/regex.html
    while re.search('[\W]', response):
        print("ERROR: Illegal query - please use only letters, numbers, and spaces")

        # ask again since incorrect
        response = input(msg)

    return response

def sanitized_input_with_spaces(msg):
    response = input(msg)
    # While response has non-alphanumeric characters
    # see https://docs.python.org/2/howto/regex.html
    while not re.search('[\w\s]', response):
        print("ERROR: Illegal query - please use only letters, numbers, and spaces")

        # ask again since incorrect
        response = input(msg)

    return response

def get_alumni_search_result_links_with_driver_with_query(driver, query):
    # handle pagination
    num_results = int(
        driver.find_element_by_css_selector(
            '#imod-view-content > div:nth-child(4) > p > strong'
            ).text.strip()
        )
    print('Search returned ' + str(num_results) + ' results')
    current_max_index = int(
        driver.find_element_by_css_selector(
            '#imod-view-content > div:nth-child(6) > p > em'
            ).text.strip().split(' - ')[1]
        )

    with open('alumni_page_queue.csv', 'w') as csvfile:
        writer = csv.writer(csvfile)
        while num_results > current_max_index:
            #imod-view-content > div.imod-directory-search-results-pager.ng-isolate-scope > div > div.imod-pager-desktop > div.imod-pager-arrow.imod-pager-next.ng-scope.disabled > a
            # got these by checking the css indeces of the search results
            start_index = 8
            end_index = 27 + 1

            for i in range(start_index, end_index):
                alumnus_link = driver.find_element_by_css_selector(
                    '#imod-view-content > div:nth-child(' + str(i) + ') > div > div > div.imod-directory-member-data-container > div.imod-directory-member-name > a'
                    )
                # get id from url
                alumnus_index = alumnus_link.get_attribute('href').split('&mid=')[1].split('#/')[0]
                writer.writerow([
                    alumnus_index,
                    query
                ])

            next_button = driver.find_element_by_css_selector(
                '#imod-view-content > div.imod-directory-search-results-pager.ng-isolate-scope > div > div.imod-pager-desktop > div.imod-pager-arrow.imod-pager-next.ng-scope > a'
                )
            next_button.click()
            current_max_index = int(
                driver.find_element_by_css_selector(
                    '#imod-view-content > div:nth-child(6) > p > em'
                    ).text.split(' - ')[1]
                )

    print('Finished saving alumni page links from search')


# Search local database
def search_locally_by_query_with_database(database):
    print('Getting local results from database')
    for result in get_search_locally_by_query_with_database(database):
        print(result)

def search_locally_by_query_with_database_to_csv(database):
    results = get_search_locally_by_query_with_database(database)
    keys = get_keys_for_database(database)
    with open('search_results.csv', 'w') as csvfile:
        print('Writing to csv file')
        writer = csv.DictWriter(csvfile, keys)
        writer.writeheader()
        writer.writerows(results)

def get_search_locally_by_query_with_database(database):
    print('You can query by any combination (one at a time) of the following keys: ')
    print_keys_for_database(database)

    keys = get_keys_for_database(database)

    query = sanitized_input_with_spaces('Please enter your search KEY (e.g. \'Employer\'): ')
    while not query in keys and query != 'done':
        print('ERROR: Please choose a search key from the above list of options. If finished, please type \'done\'.')
        query = sanitized_input_with_spaces('KEY (e.g. \'Employer\'): ')

    query_value = sanitized_input_with_spaces('What value would you like to search for?: ')
    regx = re.compile(query_value, re.IGNORECASE)
    return database.find({query : regx})

# Refactor database
def clean_colons_in_database(database):
    print('Cleaning colons - this shouldn\'t be used')
    with open('keys.json') as json_file:
        data = json.load(json_file)
        colon_keys = []
        for object in data:
            key = object['_id']['key']
            if key[-1] == ':':
                print('Updating ' + key)
                database.update_many({}, {'$rename': {key : key[:-1]}}, upsert = False)

# print keys from variety map reduce json file - must be kept updated
def print_keys_for_database(database):
    for key in get_keys_for_database(database):
        print(key)

def get_keys_for_database(database):
    keys = []
    with open('keys.json') as json_file:
        data = json.load(json_file)
        for object in data:
            key = object['_id']['key']
            keys.append(key)

    return keys

def get_mongo_alumni_collection():
    print('Connecting to Mongo')
    client = MongoClient()
    db = client.alumni
    return db.alumni

def get_driver_and_login(driver_type = 'chrome', wait_time = 30):
    # Create selenium webdriver
    driver = None
    if driver_type == 'chrome':
        driver = webdriver.Chrome()
    elif driver_type == 'phantom':
        driver = webdriver.PhantomJS()
    else:
        raise ValueError(
            'Invalid driver type; driver must be \'chrome\' or \'phantom\''
            )

    driver.implicitly_wait(wait_time)
    print('Starting crawler with %s driver and %d second implicit wait time.' % (driver_type, wait_time))
    login_to_tigernet_with_driver(driver, args.load_cookies)
    return driver

def quit_driver(driver):
    driver.quit()
    print('Closing Browser')

def main(args):
    if args.type == 'search':
        driver = get_driver_and_login(args.driver_type, args.wait_time)
        scrape_by_query_with_driver(driver)
        quit_driver(driver)
    elif args.type == 'range':
        driver = get_driver_and_login(args.driver_type, args.wait_time)
        adb = get_mongo_alumni_collection()
        scrape_from_index_with_driver_with_database(driver, adb)
        quit_driver(driver)
    elif args.type == 'queue':
        driver = get_driver_and_login(args.driver_type, args.wait_time)
        adb = get_mongo_alumni_collection()
        scrape_from_queue_with_driver_with_database(driver, adb)
        quit_driver(driver)
    elif args.type == 'local':
        adb = get_mongo_alumni_collection()
        search_locally_by_query_with_database_to_csv(adb)
    else:
        raise ValueError(
            'Argument \'type\' must be \'search\', \'range\', \'local\', or \'queue\'.'
            )

    print('Finished!')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-lc',
        '--load_cookies',
        help = 'load login cookies to speed up login and avoid duo-authentication',
        action="store_true"
        )
    parser.add_argument(
        'type',
        help = 'type of scraping to do; can be \'search\', \'range\', \'local\', or \'queue\'.'
        )
    parser.add_argument(
        '-dt',
        '--driver_type',
        help = 'type of driver to use; can be \'chrome\' (default) or \'phantom\'.'
        )
    parser.add_argument(
        '-wt',
        '--wait_time',
        help = 'number of seconds for driver to implicitly wait; defaults to 30.',
        type = int
        )
    args = parser.parse_args()
    main(args)
