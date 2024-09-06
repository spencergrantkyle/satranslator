from flask import Flask, request, render_template, send_file
from google.cloud import translate_v2 as translate
from google.cloud import speech
import os
import io
import subprocess
import time
import html

app = Flask(__name__)

app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['ALLOWED_EXTENSIONS'] = {'mp4', 'mov', 'avi'}

# Initialize the Google Translate client
translate_client = translate.Client()

# Initialize the Google Speech-to-Text client
speech_client = speech.SpeechClient()

# Function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Function to translate text
def translate_text(text, target_language='af'):
    translation = translate_client.translate(text, target_language=target_language)
    return translation['translatedText']

# Function to extract audio from video using FFMPEG and resample it to 16000 Hz
def extract_audio_from_video(filepath):
    audio_filepath = filepath.rsplit('.', 1)[0] + '.wav'  # Save audio as .wav file
    subprocess.run(['ffmpeg', '-i', filepath, '-ar', '16000', '-ac', '1', audio_filepath, '-y'], check=True)
    return audio_filepath

# Function to transcribe audio using Google Speech-to-Text
def transcribe_audio(filepath):
    with io.open(filepath, 'rb') as audio_file:
        content = audio_file.read()

    audio = speech.RecognitionAudio(content=content)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,  # Use 16000 Hz after resampling
        language_code="en-US",
    )

    response = speech_client.recognize(config=config, audio=audio)

    # Extract the transcription
    transcription = " ".join([result.alternatives[0].transcript for result in response.results])
    return transcription

# Function to create an SRT subtitle file
def create_srt_file(translated_text, filepath):
    srt_filepath = filepath.rsplit('.', 1)[0] + '.srt'  # Save subtitle as .srt file
    
    # Decode HTML entities in the translated text
    decoded_text = html.unescape(translated_text)

    lines = decoded_text.split()  # Split the decoded translation into words/phrases
    num_lines = len(lines)
    
    # Here, we assume each subtitle line lasts 2 seconds
    with open(srt_filepath, 'w') as srt_file:
        for i in range(num_lines):
            start_time = time.strftime('%H:%M:%S,000', time.gmtime(i * 2))  # Every line starts 2 seconds apart
            end_time = time.strftime('%H:%M:%S,000', time.gmtime((i + 1) * 2))  # Lasts for 2 seconds
            srt_file.write(f"{i + 1}\n{start_time} --> {end_time}\n{' '.join(lines[i:i+7])}\n\n")
    return srt_filepath

# Function to overlay subtitles using FFMPEG
def overlay_subtitles_on_video(video_filepath, srt_filepath):
    output_video_filepath = video_filepath.rsplit('.', 1)[0] + '_with_subs.mp4'  # New video with subtitles
    subprocess.run(['ffmpeg', '-i', video_filepath, '-vf', f"subtitles={srt_filepath}", output_video_filepath, '-y'], check=True)
    return output_video_filepath

# Route to display the file upload form
@app.route('/')
def upload_form():
    return render_template('upload.html')

# Route to handle file upload, transcription, translation, and subtitle generation
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    if file and allowed_file(file.filename):
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        # Step 1: Extract audio from the video
        audio_filepath = extract_audio_from_video(filepath)

        # Step 2: Transcribe the extracted audio
        transcription = transcribe_audio(audio_filepath)

        # Get the selected language from the form
        selected_language = request.form.get('language')

        # Step 3: Translate the transcription
        translated_text = translate_text(transcription, target_language=selected_language)  # Translating to Afrikaans

        # Step 4: Create the SRT file with the translated text
        srt_filepath = create_srt_file(translated_text, filepath)

        # Step 5: Overlay the subtitles onto the video
        output_video_filepath = overlay_subtitles_on_video(filepath, srt_filepath)

        # Render the HTML with the transcription, translation, and download link for the new video
        return render_template('upload.html', transcription=transcription, translation=translated_text, video_url=output_video_filepath)

# Route to download the video with subtitles
@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

# Run the app
if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    app.run(debug=True)