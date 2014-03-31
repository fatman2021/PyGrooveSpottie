import requests
import time
import yaml

from os import path
from pyquery import PyQuery as pq
from selenium import webdriver
from xml.etree import ElementTree

from creds import TINYSONG_KEY

class GrooveSpottie(object):
    def __init__(self):
        self.past_run_data_path = path.dirname(path.abspath(__file__))
        self.past_run_data = yaml.load(open(path.join(self.past_run_data_path, 'past_run_data.yaml')))

    def save_past_run_data(self):
        with open(path.join(self.past_run_data_path, 'past_run_data.yaml'), 'w') as outfile:
            outfile.write(yaml.dump(self.past_run_data, default_flow_style=True))

    def get_song_length(self, track_str):
        #Expects song_name to be in form of
        # 'artist+name+song+name'
        track_info = requests.get('https://ws.spotify.com/search/1/track?q=' + track_str)
        track_tree = ElementTree.fromstring(track_info.content)
        return float(track_tree.find(
                    '{http://www.spotify.com/ns/music/1}track').find(
                    '{http://www.spotify.com/ns/music/1}length').text)
        
    def get_tinysong_url(self, track_str):
        #Expects song_name to be in form of
        # 'artist+name+song+name'
        payload = {'key': TINYSONG_KEY, 'format': 'json'}
        return requests.get('http://tinysong.com/a/' + track_str, params=payload).json()

    def get_track_queries(self, page_pq):
        print 'Building track queries...'
        tds = page_pq('tbody tr td')
        track_queries = []
        i = 1
        clean = lambda x: x.replace('&','').replace('.','').replace(
                            "'",'').replace('(','').replace(')','').replace(
                            '?','').replace('!','').replace(',','').replace(
                            ' ','+')
        while i < len(tds):
            if i%2 == 1:
                try:
                    next_entry = clean(tds[i].find('a').text)
                except AttributeError:
                    next_entry = clean(tds[i].text)
                except UnicodeDecodeError:
                    pass
                finally:
                    i += 1
            else:
                try:
                    next_entry += '+' + clean(tds[i].text)
                    track_queries.append(next_entry)
                except UnicodeDecodeError:
                    pass
                finally:
                    i += 3
        return track_queries#[-3:-1] #<-- for testing purposes

    def get_tracks_info(self, future_selector_param=None):
        source = 'http://cd1025.com/about/playlists/now-playing'
        print 'Grabbing page source from "%s"' % source
        page_pq = pq(source)
        track_queries = self.get_track_queries(page_pq)
        tracks_info = []
        rate_limited = False
        for i, query in enumerate(track_queries):
            print 'Attempting to create entry for %s' % query
            next_entry = {}
            next_entry['track_query'] = query
            if self.past_run_data['past_queries'].get(query):
                print 'Past entry found for this query'
                next_entry['tinysong_url'] = self.past_run_data['past_queries'][query]['tinysong_url']
                tracks_info.append(next_entry)
            elif not rate_limited:
                try:
                    tinysong_url = self.get_tinysong_url(query)
                    try:
                        if 'rate limit exceeded' in tinysong_url.values()[0]:
                            print 'Tinysong API rate limit reached'
                            rate_limited = True
                            track_queries.pop(i)
                    except AttributeError:
                        if tinysong_url:
                            print 'Tinysong url found: %s' % tinysong_url
                            next_entry['tinysong_url'] = tinysong_url
                            tracks_info.append(next_entry)
                            self.past_run_data['past_queries'][query] = {'tinysong_url': tinysong_url.encode('utf-8')}
                except ValueError:
                    track_queries.pop(i)
                    print 'Tinysong API may be down'
            else:
                #Rate limit reached, pop query
                print 'No tinysong API query attempted due to rate limit reached'
                track_queries.pop(i)
        self.save_past_run_data()
        return tracks_info
            
    def main(self):
        from selenium.common.exceptions import WebDriverException, NoSuchElementException
        tracks = self.get_tracks_info()
        if not tracks:
            print 'No track information found, probably due to exceeding tinysong API rate limit'
            return
        print 'Track information gathered, launching browser...'
        w = webdriver.Firefox()
        for track in reversed(tracks):
            print 'Starting up "%s"' % track['track_query']
            w.get(track['tinysong_url'])
            time.sleep(1)
            try:
                w.switch_to_alert().accept()
            except WebDriverException:
                pass

            delay = 0
            queue_song = None
            while not queue_song and delay < 3:
                try:
                    queue_song = w.find_element_by_class_name('queue-song')
                    delay = 0
                except (NoSuchElementException, WebDriverException):
                    delay += 1
                    time.sleep(1)

            #Check there was no timeout
            if delay >= 3:
                print 'The song was not added to queue on load, attempting to play now'
                for btn in w.find_elements_by_class_name('btn-primary'):
                    if btn.text == u'Play Song':
                        btn.click()

            play_pause = None
            #Wait up to 30 seconds for the page to load
            while not play_pause and delay < 10:
                try:
                    play_pause = w.find_element_by_id('play-pause')
                    delay = 0
                except NoSuchElementException:
                    delay += 1
                    time.sleep(1)

            #Check there was no timeout
            if delay >= 10:
                print 'There seems to be an issue with Grooveshark loading'
                break

            if 'paused' in play_pause.get_attribute('class'):
                #Page did not start playing immediately
                play_pause.click()

            track_length_raw = None
            while not track_length_raw and delay < 10:
                try:
                    track_length_raw = [float(x) for x in w.find_element_by_id('time-total').text.split(':')]
                    delay = 0
                except ValueError:
                    delay +=1
                    time.sleep(1)

            #Check there was no timeout
            if delay >= 10:
                print 'There seems to be an issue with Grooveshark loading'
                break

            track['track_length'] = track_length_raw[0]*60 + track_length_raw[1]
            print 'next song starts in approx: %ss' % track['track_length']

            #Update last_song_played
            self.past_run_data['last_song_played'] = track['track_query']
            self.save_past_run_data()

            #Sleep (minus 1 to account for delay, above)
            time.sleep(track['track_length']-1)
        w.close()

if __name__ == '__main__':
    gs = GrooveSpottie()
    gs.main()
