import os.path
import whisper
from flask import Flask, jsonify, request
from flask_cors import CORS
import re
import requests
from dotenv import load_dotenv
import os
import openai

app = Flask(__name__)
CORS(app)

CORS(app, origins=["http://localhost:3000"])
load_dotenv()
OPENAI_KEY = os.getenv('OPENAI_KEY')


class InvalidPodName(Exception):
    "Invalid podcast name, please check the provided link"
    pass

class InvalidFeedUrl(Exception):
    "Unable to get RSS Feed for this podcast provided"
    pass


@app.route('/get_summary', methods=['POST'])
def get_summary():
    post_data = request.get_json()
    podcast_episode_link = post_data["podcastEpisodeLink"]
    pod_name, rss_feed = get_name_and_rss_feed_url(podcast_episode_link)
    download_podcast(pod_name, rss_feed)
    print("starting transcription")
    transcription = get_audio_transcription(pod_name)
    print("TRANSCRIPTION:\n", transcription)

    data = {"podName": pod_name, "transcription": transcription}
    # data = {"podName": "pod_name", "transcription": "transcription"}
    return jsonify(data)


def get_name_and_rss_feed_url(apple_podcast_url):
    # Extract the Apple Podcast ID from the URL
    pod_name = ""
    rss_feed_url = ""
    try:
        apple_podcast_id = re.search(r"id(\d+)", apple_podcast_url).group(1)

        #Get Pod Name
        pod_name = ""
        name_pattern = r"https://podcasts.apple.com/us/podcast/([^/]+)"
        match = re.search(name_pattern, apple_podcast_url)
        if match:
            pod_name = match.group(1)
            pod_name = pod_name.replace("-", "+")
            print("Podcast Name:", pod_name)
        else:
            raise InvalidPodName

        # Fetch podcast details using the iTunes Search API
        itunes_episode_api_url = f"https://itunes.apple.com/search?term={pod_name}&entity=podcastEpisode"
        response = requests.get(itunes_episode_api_url)
        data = response.json()

        # Extract the RSS feed URL from the response
        if data["resultCount"] > 0:
            rss_feed_url = data["results"][0]["episodeUrl"]
        else:
            raise InvalidFeedUrl
    except InvalidPodName:
        print("Exception occurred: pod_name")
    except InvalidFeedUrl:
        print("Exception occurred: feed_url")

    print(rss_feed_url)
    return pod_name, rss_feed_url


def download_podcast(pod_name, rss_feed_url):
    print("downloading")
    response = requests.get(rss_feed_url)
    file_path = os.path.join("./pod_downloads", f"{pod_name}.mp3")
    with open(file_path, 'wb') as file:
        file.write(response.content)
    print("DONE DOWNLOADING")


def get_audio_transcription(pod_name):
    model = whisper.load_model("small.en")
    result = model.transcribe(f"./pod_downloads/{pod_name}.mp3")
    transcription = result["text"][:10000]
    prompt = f"Give three bullet points from the following: {transcription}"
    openai.api_key = str(OPENAI_KEY)
    response = openai.Completion.create(
        engine="text-davinci-003",  # This is an example of a powerful engine. Replace it with the desired engine.
        prompt=prompt,
        max_tokens=256
    )
    generated_text = response["choices"][0]["text"]
    return generated_text


if __name__ == '__main__':
    app.run(debug=True)

