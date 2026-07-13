import wave
from loguru import logger
from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter

class LoggingRNNoiseFilter(RNNoiseFilter):
    def __init__(self, run_id: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.run_id = run_id
        self._raw_wav = None
        self._filtered_wav = None
        self._raw_filename = f"audio_before_rnnoise_{run_id}.wav"
        self._filtered_filename = f"audio_after_rnnoise_{run_id}.wav"

    async def filter(self, audio: bytes) -> bytes:
        # Write "before" filtering audio
        if not self._raw_wav:
            try:
                self._raw_wav = wave.open(self._raw_filename, "wb")
                self._raw_wav.setnchannels(1)
                self._raw_wav.setsampwidth(2)  # 16-bit PCM
                self._raw_wav.setframerate(self._sample_rate)
            except Exception as e:
                logger.error(f"Failed to open raw wav file: {e}")
        
        if self._raw_wav:
            self._raw_wav.writeframes(audio)

        # Call the base filter
        filtered_audio = await super().filter(audio)

        # Write "after" filtering audio
        if len(filtered_audio) > 0:
            if not self._filtered_wav:
                try:
                    self._filtered_wav = wave.open(self._filtered_filename, "wb")
                    self._filtered_wav.setnchannels(1)
                    self._filtered_wav.setsampwidth(2)  # 16-bit PCM
                    self._filtered_wav.setframerate(self._sample_rate)
                except Exception as e:
                    logger.error(f"Failed to open filtered wav file: {e}")
            
            if self._filtered_wav:
                self._filtered_wav.writeframes(filtered_audio)

        return filtered_audio

    async def stop(self):
        if self._raw_wav:
            try:
                self._raw_wav.close()
                logger.info(f"[AUDIO] Saved raw input to {self._raw_filename}")
            except Exception as e:
                logger.error(f"Error closing raw wav: {e}")
            self._raw_wav = None

        if self._filtered_wav:
            try:
                self._filtered_wav.close()
                logger.info(f"[AUDIO] Saved filtered input to {self._filtered_filename}")
            except Exception as e:
                logger.error(f"Error closing filtered wav: {e}")
            self._filtered_wav = None

        await super().stop()
