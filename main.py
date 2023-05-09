import os.path
import whisper #listed under openai-whisper in requirements
from flask import Flask, jsonify, request, abort
from flask_cors import CORS, cross_origin
import re
import requests
from dotenv import load_dotenv
import os
import openai
import logging
import torch
import time
import firebase_admin
from firebase_admin import firestore, credentials


# Local
ALLOW = 'http://localhost:3000'
TEST_LOCAL = "localhost"
os.environ['FIRESTORE_EMULATOR_HOST'] = f'{TEST_LOCAL}:8081'

# Production
# ALLOW = 'https://podcast-university.web.app'


app = Flask(__name__)
# cors = CORS(app, resources={r"/*": {"origins": f"{ALLOW}"}})
# CORS(app, resources={r'*': {'origins': '*'}})
CORS(app)
TOKEN_LIMIT = 4096
WORD_CHUNK = 2700
TOKEN_WORD_RATIO = 1.41
RESIZED_TXT = "_resized.txt"
load_dotenv()
OPENAI_KEY = os.environ.get('OPENAI_KEY')
HOME = os.environ.get('APP_HOME')
APP_DIR = os.path.abspath(os.path.dirname(__file__))

# initialize firebase admin-sdk
# local
cred = credentials.Certificate(f"./firebase_credentials.json")

# production
# cred = credentials.Certificate(f"{HOME}/firebase_credentials.json")

firebase_app = firebase_admin.initialize_app(cred)
db = firestore.client()


class InvalidPodName(Exception):
    "Invalid podcast name, please check the provided link"
    pass


class InvalidFeedUrl(Exception):
    "Unable to get RSS Feed for this podcast provided"
    pass


@app.route('/')
def hello_world():
    return 'PodcastUni api'


@app.route('/get_summary', methods=['POST'])
def get_summary():
    print("GET_SUMMARY")
    logging.getLogger('flask_cors').level = logging.DEBUG
    # https://podcasts.apple.com/us/podcast/the-acquired-podcast-hosts-how-they-started-and/id1469759170?i=1000607682857
    # parse out request data
    post_data = request.json
    print(post_data)
    podcast_episode_link = post_data['podcastEpisodeLink']
    bullet_points = post_data['numBulletPoints']
    uid = post_data['uid']

    # get podcast rss feed info and name
    pod_name, rss_feed = get_name_and_rss_feed_url(podcast_episode_link)
    if pod_name is None or rss_feed is None:
        print("POD NAME OR RSS_FEED NO GOOD")
        abort(500, descpription="Unable to get the podcast name or feed")

    # handle podcast transcription and audio contents
    check_podcast_transcription_and_audio_contents(rss_feed, pod_name)

    # get bullet points
    bullet_points_summary = get_bullet_summary(f"{pod_name}{RESIZED_TXT}", bullet_points)

    # clean up
    final_transcription = cleanup_bullet_points(bullet_points_summary)

    # Remove pod download after all processing has been done
    pod_audio_removal(pod_name)

    # Convert pod_name to something usable for the user
    # pod_name = pod_name_normal_conversion(pod_name)

    data = {"podName": pod_name, "transcription": bullet_points_summary}

    if len(bullet_points_summary) < 1:
        abort(500, description="An error occured while processing the request")

    summary_item = {
        "uid": uid,
        "pod_name": pod_name,
        "summary": bullet_points_summary,
        "summary_type": bullet_points
    }

    db.collection(f"summaries").add(summary_item)
    db.document(f"users/{uid}").update({"requesting": False})
    return jsonify(data)

def pod_audio_removal(pod_name):
    file_path = f"{APP_DIR}/pod_downloads/{pod_name}.mp3"
    if os.path.isfile(file_path):
        os.remove(file_path)


def cleanup_bullet_points(bullet_points):
    print("BULLET POINTS:\n", bullet_points)
    lines = bullet_points.splitlines()
    non_empty_lines = [line for line in lines if line.strip()]
    final_bullet_points = "\n".join(non_empty_lines)
    return final_bullet_points


def get_name_and_rss_feed_url(apple_podcast_url):
    # Extract the Apple Podcast ID from the URL
    pod_name = ""
    rss_feed_url = ""
    try:
        pattern = r'i=(\d+)'
        match = re.search(pattern, apple_podcast_url)
        if match:
            # Fetch podcast details using the iTunes Search API
            itunes_episode_api_url = f"https://itunes.apple.com/search?term={match.group(1)}&entity=podcastEpisode"
            response = requests.get(itunes_episode_api_url)
            data = response.json()
            # Extract the RSS feed URL from the response
            if data["resultCount"] > 0:
                rss_feed_url = data["results"][0]["episodeUrl"]
                pod_name = data["results"][0]["trackName"]
            else:
                raise InvalidFeedUrl
        else:
            raise InvalidPodName
    except InvalidPodName:
        print("Exception occurred: pod_name")
    except InvalidFeedUrl:
        print("Exception occurred: feed_url")
    print("PodName:", pod_name, "\n", "MP3 URL:", rss_feed_url)
    return pod_name, rss_feed_url


def download_podcast(pod_name, rss_feed_url):
    print("downloading")
    response = requests.get(rss_feed_url)
    if not os.path.exists(f'{APP_DIR}/pod_downloads'):
        print("CREATING POD_DOWNLOADS DIRECTORY")
        os.mkdir(f'{APP_DIR}/pod_downloads')
    file_path = os.path.join(f"{APP_DIR}/pod_downloads", f"{pod_name}.mp3")
    with open(file_path, 'wb') as file:
        file.write(response.content)
    print("DONE DOWNLOADING")


def check_podcast_transcription_and_audio_contents(rss_feed, pod_name):
    file_path_transcription = f"{HOME}/transcriptions/{pod_name}.txt"
    if not os.path.exists(f'{APP_DIR}/pod_downloads'):
        print("CREATING pod_downloads DIRECTORY")
        os.mkdir(f'{APP_DIR}/pod_downloads')
    file_path_pod_audio_download = f"{APP_DIR}/pod_downloads/{pod_name}.mp3"
    if not os.path.isfile(file_path_transcription):
        if not os.path.isfile(file_path_pod_audio_download):
            download_podcast(pod_name, rss_feed)
            print("Transcribing after download")
            set_rawtrans_and_TLtrans(pod_name)
        else:
            print("Audio already exists, transcribing now")
            set_rawtrans_and_TLtrans(pod_name)


def set_rawtrans_and_TLtrans(pod_name):
    # set raw transcription of audio file
    torch.cuda.is_available()
    print("AVAILABLE: ",  torch.cuda.is_available())
    start = time.time()
    print("start transcriptions:", start)
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    model = whisper.load_model("base.en", device=DEVICE)
    result = model.transcribe(f"{APP_DIR}/pod_downloads/{pod_name}.mp3")
    print("end transcription:", time.time())
    print("transcription total time:", time.time()-start)
    transcription = result["text"]

    if not os.path.exists(f'{APP_DIR}/transcriptions'):
        print("CREATING transcriptions DIRECTORY")
        os.mkdir(f'{APP_DIR}/transcriptions')
    with open(f'{APP_DIR}/transcriptions/{pod_name}.txt', 'w') as file:
        file.write(transcription)

    # chunked_transcription = chunkify(transcription, num_bullets)
    '''
        1.) get total tokens of transcription = 1.41 * total_words
        2.) break up transcription into 4096 token chunks to be sent off for summerization in the total token size being
            4096/total_chunks and write to string variable which is then written to file
        3.) send off final string variable for requested amount of bullet summerization
    '''
    # chunked_transcription = resize_transcription(f"{pod_name}.txt")
    chunked_transcription = resize_transcription(f"{pod_name}.txt")
    if not os.path.exists(f'{APP_DIR}/transcriptions_resized'):
        print("CREATING transcriptions_resized DIRECTORY")
        os.mkdir(f'{APP_DIR}/transcriptions_resized')
    with open(f'{APP_DIR}/transcriptions_resized/{pod_name}{RESIZED_TXT}', 'w') as resized_transcription:
        resized_transcription.write(chunked_transcription)


def summarize_text(text, num_words_to_summarize_to):
    prompt = f"please summarize the following in {str(num_words_to_summarize_to)} or less: {text}"
    openai.api_key = str(OPENAI_KEY)
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        temperature=0.2,
        max_tokens=round(num_words_to_summarize_to * 1.41),
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None

    )

    generated_text = response["choices"][0]["text"]
    return generated_text


def get_bullet_summary(txt_file, num_bullets):
    if not os.path.exists(f'{APP_DIR}/transcriptions_resized'):
        print("CREATING transcriptions_resized DIRECTORY")
        os.mkdir(f'{APP_DIR}/transcriptions_resized')
    with open(f'{APP_DIR}/transcriptions_resized/'+txt_file, 'r') as file:
        content = file.read()


    prompt = f"Summarize the following into {str(num_bullets)} bullet points:\n\n{content}\n"
    openai.api_key = str(OPENAI_KEY)
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        temperature=0.0,
        max_tokens=512,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        best_of=1
    )
    generated_text = response["choices"][0]["text"]
    response.choices[0].text.strip()
    return generated_text


def resize_transcription(txt_file) -> str:
    with open(f'{APP_DIR}/transcriptions/{txt_file}', 'r') as file:
        transcription = str(file.read())
    total_words = total_num_words(transcription)
    # 4096 tokens is equivalent to 2900 words, 2900 word chunks will be how we chunk out
    # num_chunks = 1 if (total_words * TOKEN_WORD_RATIO)//TOKEN_LIMIT == 0 else (total_words * TOKEN_WORD_RATIO)//TOKEN_LIMIT
    # if num_chunks > 1:
    #     last_chunk = (total_words * TOKEN_WORD_RATIO)%TOKEN_LIMIT
    # else:
    #     last_chunk = 0
    # total_chunks = int(num_chunks+1)
    # chunk_size = TOKEN_LIMIT/total_chunks

    num_whole_chunks = 1 if (total_words * WORD_CHUNK) < 2900 else total_words//WORD_CHUNK
    remainder_chunk = total_words % WORD_CHUNK
    total_chunks = num_whole_chunks + 1
    if total_chunks > 1:
        summarization_word_size = round(WORD_CHUNK/total_chunks)
    else:
        summarization_word_size = total_words


    chunk_str = ""
    start = 0
    # TODO: this can be improved by summarizing by the large chunks first then summarize the last chunk
    if total_chunks > 1:
        for i in range(total_chunks):
            chunk_itr = i+1
            if chunk_itr != total_chunks:
                end = chunk_itr * WORD_CHUNK
                chunk_str += summarize_text(transcription[start:end], summarization_word_size)
                start = end

            if chunk_itr == total_chunks:
                end = remainder_chunk
                chunk_str += summarize_text(transcription[start:end], summarization_word_size)
    else:
        return transcription
    return chunk_str


def total_num_words(string):
    return len(string.split())


if __name__ == '__main__':
    # production
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

    # local with phone
    # app.run(host="127.0.0.1", debug=True)

    # local
    app.run(debug=True)
