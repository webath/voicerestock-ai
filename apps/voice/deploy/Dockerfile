# VoiceRestock voice agent. Χτίζεται ΠΑΝΩ στο image του SafeVoice (ίδιες εξαρτήσεις: pipecat 1.9, livekit,
# google-genai), οπότε δεν ξαναστήνεται τίποτα και ο SafeVoice μένει ανέγγιχτος στο greek-agent:safevoice.
ARG BASE=greek-agent:safevoice
FROM ${BASE}
COPY vr_core.py bot_voicerestock.py ./
CMD ["python", "bot_voicerestock.py"]
