/**
 * CulinaryOS - Multilingual Voice Studio Module
 * Supports Telugu, Hindi, English, Tamil, and Kannada
 * Provides Recording, Speech Recognition, Native TTS, Wave Animation & Presets
 */

const VoiceStudio = {
  activeLang: 'te',
  isRecording: false,
  mediaRecorder: null,
  audioChunks: [],
  recognition: null,
  liveTranscript: '',

  langConfigs: {
    te: {
      name: 'Telugu (తెలుగు)',
      speechCode: 'te-IN',
      sampleText: 'నమస్కారం, రేపు 2 భోజనాలు కావాలి, ఒకదాంట్లో వేరుశెనగలు ఉండకూడదు. 42 రెసిడెన్సీ రోడ్డుకి పంపండి.',
      presets: [
        { title: 'New Order with Peanut Allergy', text: 'నమస్కారం, రేపు 2 భోజనాలు కావాలి, ఒకదాంట్లో వేరుశెనగలు ఉండకూడదు. 42 రెసిడెన్సీ రోడ్డుకి పంపండి.' },
        { title: 'Quantity Reduction (Food Waste Check)', text: 'దయచేసి ఒక భోజనం తగ్గించండి, మొత్తం 1 చాలు.' },
        { title: 'Address & Delivery Time update', text: 'డెలివరీ సమయం మధ్యాహ్నం 1:00 గంట తర్వాత చేయండి.' }
      ]
    },
    hi: {
      name: 'Hindi (हिन्दी)',
      speechCode: 'hi-IN',
      sampleText: 'कल दोपहर 4 थाली चाहिए, 12:30 के बाद 12 मालवीय नगर पर डिलीवर करवा दें। बच्चों के लिए मिर्च कम रखिएगा।',
      presets: [
        { title: 'New Order with Mild Spice', text: 'कल दोपहर 4 थाली चाहिए, 12:30 के बाद 12 मालवीय नगर पर डिलीवर करवा दें। बच्चों के लिए मिर्च कम रखिएगा।' },
        { title: 'Quantity Reduction to 2', text: 'कृपया 2 थाली कम कर दीजिए, हमें केवल 2 थाली ही चाहिए।' },
        { title: 'Status & ETA Inquiry', text: 'नमस्ते, हमारे खाने की तैयारी कैसी चल रही है? कब तक पहुँचेगा?' }
      ]
    },
    en: {
      name: 'English',
      speechCode: 'en-IN',
      sampleText: 'Three meals tomorrow, mild spice for grandma, deliver to 42 Residency Road after 1 PM.',
      presets: [
        { title: 'Allergen Alert & Quantity', text: 'Three meals tomorrow, peanut allergy in one meal, deliver to 42 Residency Road after 1 PM.' },
        { title: 'Reduce Quantity by 1', text: 'Please reduce quantity from 3 to 2 meals. One guest canceled.' },
        { title: 'Address Ambiguity Resolution', text: 'Please confirm delivery to my home address at Indiranagar, not office.' }
      ]
    },
    ta: {
      name: 'Tamil (தமிழ்)',
      speechCode: 'ta-IN',
      sampleText: 'நாளை மதியம் இரண்டு சாப்பாடு வேண்டும், காரம் குறைவாக இருக்கட்டும். 15 காந்தி ரோடு முகவரிக்கு அனுப்பவும்.',
      presets: [
        { title: 'New Lunch Order', text: 'நாளை மதியம் இரண்டு சாப்பாடு வேண்டும், காரம் குறைவாக இருக்கட்டும். 15 காந்தி ரோடு முகவரிக்கு அனுப்பவும்.' },
        { title: 'Reduce Quantity', text: 'ஒரு சாப்பாடு குறைக்கவும், மொத்தம் ஒன்று போதும்.' }
      ]
    },
    kn: {
      name: 'Kannada (ಕನ್ನಡ)',
      speechCode: 'kn-IN',
      sampleText: 'ನಾಳೆ ಮಧ್ಯಾಹ್ನ ಮೂರು ಊಟ ಬೇಕು, 10 ಎಂಜಿ ರಸ್ತೆಗೆ 12:30 ನಂತರ ಡೆಲಿವರಿ ಮಾಡಿ.',
      presets: [
        { title: 'New Meal Booking', text: 'ನಾಳೆ ಮಧ್ಯಾಹ್ನ ಮೂರು ಊಟ ಬೇಕು, 10 ಎಂಜಿ ರಸ್ತೆಗೆ 12:30 ನಂತರ ಡೆಲಿವರಿ ಮಾಡಿ.' },
        { title: 'Change to 2 Meals', text: 'ದಯವಿಟ್ಟು ಒಂದು ಊಟ ಕಡಿಮೆ ಮಾಡಿ, ಎರಡು ಮಾತ್ರ ಕಳುಹಿಸಿ.' }
      ]
    }
  },

  init() {
    this.setupSpeechRecognition();
  },

  setLanguage(langCode) {
    if (!this.langConfigs[langCode]) return;
    this.activeLang = langCode;
    
    // Update pill buttons
    document.querySelectorAll('.lang-pill-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.lang === langCode);
    });

    // Update Presets
    this.renderPresets();

    // Reconfigure recognition
    if (this.recognition) {
      this.recognition.lang = this.langConfigs[langCode].speechCode;
    }

    const input = document.getElementById('voice-custom-text');
    if (input) {
      input.placeholder = `Speak or type in ${this.langConfigs[langCode].name}...`;
    }
  },

  setupSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('SpeechRecognition API not available in this browser.');
      return;
    }

    this.recognition = new SpeechRecognition();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = this.langConfigs[this.activeLang].speechCode;

    this.recognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          this.liveTranscript += event.results[i][0].transcript + ' ';
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      const display = (this.liveTranscript + ' ' + interim).trim();
      const txtArea = document.getElementById('voice-custom-text');
      if (txtArea) txtArea.value = display;
    };

    this.recognition.onerror = (e) => {
      console.warn('Speech recognition error:', e.error);
    };
  },

  async toggleRecording(orderId) {
    const recBtn = document.getElementById('btn-toggle-record');
    const visualizer = document.getElementById('voice-visualizer');

    if (this.isRecording) {
      // STOP RECORDING
      this.isRecording = false;
      if (recBtn) {
        recBtn.innerHTML = '🎙️ <span>Start Recording Voice Note</span>';
        recBtn.classList.remove('btn-pill-reset');
      }
      if (visualizer) visualizer.classList.remove('recording');

      if (this.recognition) {
        try { this.recognition.stop(); } catch (_) {}
      }

      if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
        this.mediaRecorder.stop();
      } else {
        // Fallback synthetic upload if mediaRecorder was not initialized
        this.finalizeAndSendVoice(orderId);
      }
    } else {
      // START RECORDING
      this.isRecording = true;
      this.liveTranscript = '';
      if (recBtn) {
        recBtn.innerHTML = '⏹️ <span>Stop & Process Voice</span>';
        recBtn.classList.add('btn-pill-reset');
      }
      if (visualizer) visualizer.classList.add('recording');

      if (this.recognition) {
        try {
          this.recognition.lang = this.langConfigs[this.activeLang].speechCode;
          this.recognition.start();
        } catch (_) {}
      }

      try {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          this.audioChunks = [];
          this.mediaRecorder = new MediaRecorder(stream);
          this.mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) this.audioChunks.push(e.data);
          };
          this.mediaRecorder.onstop = () => {
            const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
            stream.getTracks().forEach(track => track.stop());
            this.sendAudioBlob(orderId, audioBlob);
          };
          this.mediaRecorder.start();
        }
      } catch (err) {
        console.warn('Microphone permission not granted or unavailable. Using synthetic audio fallback.', err);
      }
    }
  },

  createSyntheticWavBlob() {
    // 1-second 44.1kHz silent/sine WAV blob for standard multi-part payload compliance
    const sampleRate = 8000;
    const numSamples = sampleRate * 1; // 1 second
    const buffer = new ArrayBuffer(44 + numSamples * 2);
    const view = new DataView(buffer);

    const writeString = (view, offset, string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };

    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + numSamples * 2, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, 'data');
    view.setUint32(40, numSamples * 2, true);

    for (let i = 0; i < numSamples; i++) {
      const s = Math.sin(2 * Math.PI * 440 * (i / sampleRate));
      view.setInt16(44 + i * 2, s * 0x3FFF, true);
    }

    return new Blob([view], { type: 'audio/wav' });
  },

  async finalizeAndSendVoice(orderId) {
    const textInput = document.getElementById('voice-custom-text');
    const transcript = (textInput && textInput.value.trim()) || this.liveTranscript.trim();
    if (!transcript) {
      // Never send a canned sentence as if the customer had said it: load it into the box so it is visible and editable.
      if (textInput) textInput.value = this.langConfigs[this.activeLang].sampleText;
      showToast('Loaded a sample voice note - edit it or press Upload Note again to send it.', 'info');
      return;
    }
    const syntheticWav = this.createSyntheticWavBlob();
    await this.sendAudioBlob(orderId, syntheticWav, transcript);
  },

  async sendAudioBlob(orderId, blob, forcedTranscript = null) {
    showToast(`Processing ${this.langConfigs[this.activeLang].name} voice note...`, 'info');
    const textInput = document.getElementById('voice-custom-text');
    // A real microphone recording is sent with whatever transcript we actually have (maybe none): the server
    // listens to the audio in live mode, and refuses (instead of inventing an order) in mock mode.
    const isRealRecording = forcedTranscript === null;
    const transcript = forcedTranscript || (textInput && textInput.value.trim()) || this.liveTranscript.trim() || '';

    try {
      if (!orderId) {
        const created = await API.createOrder('Customer (Voice)', this.activeLang);
        orderId = created.order_id;
        if (window.App) window.App.currentOrderId = orderId;
      }
      const ext = ((blob.type || 'audio/wav').split('/')[1] || 'wav').split(';')[0];
      const file = new File([blob], `voice_${Date.now()}.${ext}`, { type: blob.type || 'audio/wav' });
      await API.uploadFile(orderId, 'customer', file, transcript, this.activeLang, { useSample: !isRealRecording });
      showToast('Voice message parsed and processed by AI!', 'success');
      
      // Auto speak AI confirmation response
      setTimeout(() => {
        this.speakText(`Your order has been updated. Processed in ${this.langConfigs[this.activeLang].name}.`, this.activeLang);
      }, 500);

      // Trigger app refresh
      if (window.App) {
        await window.App.loadAllData();
        await window.App.selectOrder(orderId);
      }
    } catch (err) {
      console.error('Audio upload error:', err);
    }
  },

  renderPresets() {
    const container = document.getElementById('voice-presets-list');
    if (!container) return;

    const config = this.langConfigs[this.activeLang];
    container.innerHTML = config.presets.map((p, idx) => `
      <div class="preset-chip" onclick="VoiceStudio.selectPreset('${idx}')">
        <div>
          <div style="font-weight:600; color:var(--text-main); margin-bottom:0.2rem;">${p.title}</div>
          <div style="color:var(--text-muted); font-size:0.75rem;">"${p.text}"</div>
        </div>
        <button class="btn-pill" style="font-size:0.7rem; padding:0.2rem 0.5rem;" onclick="event.stopPropagation(); VoiceStudio.speakText('${p.text.replace(/'/g, "\\'")}', '${this.activeLang}')">🔊</button>
      </div>
    `).join('');
  },

  selectPreset(index) {
    const config = this.langConfigs[this.activeLang];
    const preset = config.presets[index];
    if (!preset) return;

    const input = document.getElementById('voice-custom-text');
    if (input) input.value = preset.text;
    showToast(`Loaded preset: "${preset.title}"`, 'info');
  },

  speakText(text, lang = 'en') {
    if (!('speechSynthesis' in window)) {
      showToast('Speech synthesis is not supported on this browser', 'warning');
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    const speechCode = this.langConfigs[lang] ? this.langConfigs[lang].speechCode : 'en-US';
    utterance.lang = speechCode;
    utterance.rate = 0.95;
    window.speechSynthesis.speak(utterance);
    showToast(`Playing speech in ${speechCode}...`, 'info');
  }
};

window.VoiceStudio = VoiceStudio;
