from django.contrib.auth.models import User
from integrations.models import Artist, Release
from spotipy.oauth2 import SpotifyOAuth
import datetime
import os
import requests
import time
from dateutil.parser import parse

class SpotifyFetcher():
    def fetch(user_id):
        user = User.objects.get(pk=user_id)

        # get integration
        integration = user.integration_set.get(identifier='spotify')

        # refresh token
        client_id = os.environ.get('SPOTIFY_KEY', '')
        client_secret = os.environ.get('SPOTIFY_SECRET', '')
        sp_oauth = SpotifyOAuth(client_id, client_secret, None)
        token_info = sp_oauth.refresh_access_token(integration.refresh_token)

        integration.access_token = token_info['access_token']
        integration.refresh_token = token_info['refresh_token']
        integration.save()

        # load all artists
        artists = []
        all_artists_loaded = False
        limit = 50
        token = integration.access_token
        url = f"https://api.spotify.com/v1/me/following?type=artist&limit={limit}&access_token={token}"

        while not all_artists_loaded:
            response = requests.get(url).json()['artists']
            current_request_artists = response['items']
            artists += current_request_artists
            if response['next']:
                url = response['next'] + f"&access_token={token}"
            else:
                all_artists_loaded = True

        # save or update loaded artists
        for artist in artists:
            find_by = {"integration": integration, "integration_artist_id": artist["id"]}
            update = {"name": artist["name"]}
            if Artist.objects.filter(**find_by).exists():
                Artist.objects.filter(**find_by).update(**update)
            else:
                Artist.objects.create(**update, **find_by)

        artists = integration.artist_set.all()

        for artist in artists:
            # load releases
            releases = []
            all_releases_loaded = False
            limit = 50
            artist_id = artist.integration_artist_id
            url = f"https://api.spotify.com/v1/artists/{artist_id}/albums?limit={limit}&access_token={token}"

            while not all_releases_loaded:
                response = requests.get(url).json()
                try:
                    current_request_releases = response['items']
                except KeyError:
                    raise Exception(f'KeyError "items" (url: {url}, artist: {artist.name}, response: {response})')
                releases += current_request_releases
                if response['next']:
                    url = response['next'] + f"&access_token={token}"
                else:
                    all_releases_loaded = True
                time.sleep(0.1)

            # save or update releases
            for release in releases:
                find_by = {"artist": artist, "integration_release_id": release["id"]}

                try:
                    release_date = parse(release['release_date'])
                except ValueError:
                    release_date = str(datetime.date.today())

                cover_url = release['images']
                if len(cover_url) > 0:
                    cover_url = max(release['images'], key=lambda image: image['width'])['url']
                else:
                    cover_url = ''

                update = {
                    "title": release["name"],
                    "cover_url": cover_url,
                    "date": release_date,
                    "release_type": release["album_type"],
                    "integration_url": release['external_urls']['spotify'],
                }
                if Release.objects.filter(**find_by).exists():
                    Release.objects.filter(**find_by).update(**update)
                else:
                    Release.objects.create(**update, **find_by)
