import requests
import time
from pyquery import PyQuery as pq
from selenium import webdriver
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from xml.etree import ElementTree

from creds import TINYSONG_KEY

class GrooveSpottie(object):
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
                finally:
                    i += 1
            else:
                next_entry += '+' + clean(tds[i].text)
                track_queries.append(next_entry)
                i += 3
        return track_queries#[-3:-1] #<-- for testing purposes
                    
    def get_tracks_info(self, future_selector_param=None):
        source = 'http://cd1025.com/about/playlists/now-playing'
        print 'Grabbing page source from "%s"' % source
        page_pq = pq(source)
        track_queries = self.get_track_queries(page_pq)
        tracks_info = []
        for i, query in enumerate(track_queries):
            print 'Attempting to create entry for %s' % query
            next_entry = {}
            next_entry['track_query'] = query
            try:
                tinysong_url = self.get_tinysong_url(query)
                if tinysong_url:
                    next_entry['tinysong_url'] = tinysong_url
                    tracks_info.append(next_entry)
                else:
                    track_queries.pop(i)
            except ValueError:
                track_queries.pop(i)
        return tracks_info
            
    def main(self):
        tracks = self.get_tracks_info()
        print 'Track information gathered, launching browser...'
        w = webdriver.Firefox()
        for track in reversed(tracks):
            print 'Starting up "%s"' % track['track_query']
            w.get(track['tinysong_url'])
            try:
                w.switch_to_alert().accept()
            except WebDriverException:
                pass

            delay = 0
            play_pause = None
            #Wait up to 30 seconds for the page to load
            while not play_pause and delay < 30:
                try:
                    play_pause = w.find_element_by_id('play-pause')
                except NoSuchElementException:
                    delay += 3
                    time.sleep(3)

            #Check there was no timeout
            if delay >= 30:
                print 'There seems to be an issue with Grooveshark loading'
                break

            if 'paused' in play_pause.get_attribute('class'):
                #Page did not start playing immediately
                play_pause.click()

            delay = 0
            track_length_raw = None
            while not track_length_raw and delay < 10:
                try:
                    track_length_raw = [float(x) for x in w.find_element_by_id('time-total').text.split(':')]
                except ValueError:
                    delay +=1
                    time.sleep(1)

            #Check there was no timeout
            if delay >= 10:
                print 'There seems to be an issue with Grooveshark loading'
                break

            track['track_length'] = track_length_raw[0]*60 + track_length_raw[1]
            print 'next song starts in approx: %ss' % track['track_length']
            #Sleep (minus 1 to account for delay, above)
            time.sleep(track['track_length']-1))
        w.close()

if __name__ == '__main__':
    gs = GrooveSpottie()
    gs.main()
