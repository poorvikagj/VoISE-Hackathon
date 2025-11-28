import React, { useState, useRef } from 'react';
import '@/App.css';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { Mic, Upload, FileAudio, Loader2, Plus, X, AlertCircle, Info, RefreshCw } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const NON_VERBAL_OPTIONS = [
  'Clutching chest',
  'Limping',
  'Coughing',
  'Pointing to throat',
  'Shallow breathing',
  'Dizziness',
  'Holding abdomen',
  'Grimacing in pain',
  'Sweating profusely',
  'Pale appearance'
];

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [transcript, setTranscript] = useState('');
  const [selectedActions, setSelectedActions] = useState([]);
  const [customAction, setCustomAction] = useState('');
  const [loading, setLoading] = useState(false);
  const [clinicalData, setClinicalData] = useState(null);
  const [micStatus, setMicStatus] = useState('unknown');
  
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const fileInputRef = useRef(null);

  const checkMicrophone = async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setMicStatus('not-supported');
        toast.error('Your browser does not support microphone access');
        return;
      }

      // Try to get permission
      toast.info('Requesting microphone access... Please click "Allow" when prompted.');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Success - stop the stream immediately
      stream.getTracks().forEach(track => track.stop());
      setMicStatus('granted');
      toast.success('Microphone access granted! You can now record audio.');
    } catch (error) {
      console.error('Microphone check error:', error);
      
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        setMicStatus('denied');
        toast.error('Microphone access denied. Please click the camera/mic icon in your browser address bar and allow microphone access.');
      } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
        setMicStatus('not-found');
        toast.error('No microphone detected. Please connect a microphone or use Upload Audio instead.');
      } else {
        setMicStatus('error');
        toast.error('Could not access microphone: ' + error.message);
      }
    }
  };

  const startRecording = async () => {
    try {
      // Check if mediaDevices is supported
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        toast.error('Your browser does not support audio recording. Please use a modern browser like Chrome, Firefox, or Edge.');
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setMicStatus('granted');
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        setAudioBlob(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
      toast.success('Recording started');
    } catch (error) {
      console.error('Recording error:', error);
      
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        toast.error('Microphone access denied. Please allow microphone permissions in your browser settings and try again.');
      } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
        toast.error('No microphone found. Please connect a microphone or use the Upload Audio option instead.');
      } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
        toast.error('Microphone is being used by another application. Please close other apps and try again.');
      } else {
        toast.error('Failed to access microphone. Try uploading an audio file instead.');
      }
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      toast.success('Recording stopped');
    }
  };

  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (file) {
      setAudioBlob(file);
      toast.success('Audio file uploaded');
    }
  };

  const transcribeAudio = async () => {
    if (!audioBlob) {
      toast.error('Please record or upload audio first');
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'audio.webm');

      const response = await axios.post(`${API}/transcribe`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setTranscript(response.data.transcript);
      toast.success('Transcription complete');
    } catch (error) {
      toast.error('Transcription failed');
      console.error('Transcription error:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleAction = (action) => {
    setSelectedActions(prev =>
      prev.includes(action)
        ? prev.filter(a => a !== action)
        : [...prev, action]
    );
  };

  const addCustomAction = () => {
    if (customAction.trim()) {
      setSelectedActions(prev => [...prev, customAction.trim()]);
      setCustomAction('');
    }
  };

  const generateNotes = async () => {
    if (!transcript) {
      toast.error('Please transcribe audio first');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post(`${API}/generate-notes`, {
        transcript,
        observed_actions: selectedActions.join(', ')
      });

      setClinicalData(response.data);
      toast.success('Clinical notes generated');
    } catch (error) {
      toast.error('Failed to generate notes');
      console.error('Generation error:', error);
    } finally {
      setLoading(false);
    }
  };

  const clearAll = () => {
    setAudioBlob(null);
    setTranscript('');
    setSelectedActions([]);
    setCustomAction('');
    setClinicalData(null);
    toast.success('All data cleared');
  };

  return (
    <div className="app-container">
      <header className="header">
        <div className="header-content">
          <div className="header-icon">
            <FileAudio className="icon" />
          </div>
          <div>
            <h1 className="header-title">Pre-Charting AI Assistant</h1>
            <p className="header-subtitle">AI-powered clinical documentation from audio consultations</p>
          </div>
        </div>
      </header>

      <main className="main-content">
        <div className="grid-layout">
          {/* Audio Input Section */}
          <Card className="card" data-testid="audio-input-card">
            <CardHeader>
              <CardTitle className="card-title">Audio Input</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="info-banner" data-testid="mic-info-banner">
                <Info className="info-icon" />
                <div className="info-content">
                  <p className="info-text">
                    <strong>Microphone Access:</strong> Click "Test Microphone" first to grant permissions. 
                    If blocked, click the camera/mic icon in your browser address bar.
                  </p>
                  {micStatus === 'granted' && (
                    <Badge className="status-badge success" data-testid="mic-status-granted">
                      ✓ Microphone Ready
                    </Badge>
                  )}
                  {micStatus === 'denied' && (
                    <div className="space-y-2">
                      <Badge className="status-badge error" data-testid="mic-status-denied">
                        ✗ Access Denied
                      </Badge>
                      <div className="troubleshoot-box">
                        <strong>To fix this:</strong>
                        <ol className="troubleshoot-steps">
                          <li>Look for the <strong>🔒 lock icon</strong> or <strong>🎤 microphone icon</strong> in your browser's address bar (next to the URL)</li>
                          <li>Click on it</li>
                          <li>Find "Microphone" and change it from "Block" to <strong>"Allow"</strong></li>
                          <li>Refresh this page or click "Test Microphone" again</li>
                        </ol>
                        <p className="troubleshoot-note">📍 The icon is usually on the left side of the address bar where it shows "https://"</p>
                      </div>
                    </div>
                  )}
                  {micStatus === 'not-found' && (
                    <Badge className="status-badge warning" data-testid="mic-status-not-found">
                      ⚠ No Microphone Found
                    </Badge>
                  )}
                </div>
              </div>
              <div className="button-group">
                <Button
                  data-testid="test-microphone-button"
                  onClick={checkMicrophone}
                  variant="outline"
                  className="test-mic-btn"
                  disabled={loading}
                >
                  <Mic className="btn-icon" />
                  Test Microphone
                </Button>
                {micStatus === 'denied' && (
                  <Button
                    data-testid="reset-permissions-button"
                    onClick={() => {
                      setMicStatus('unknown');
                      toast.info('Click the lock/microphone icon in the address bar, then allow microphone access, then test again.');
                    }}
                    variant="outline"
                    className="reset-btn"
                  >
                    <RefreshCw className="btn-icon" />
                    Try Again
                  </Button>
                )}
              </div>
              <Separator className="my-2" />
              <div className="button-group">
                <Button
                  data-testid="record-button"
                  onClick={isRecording ? stopRecording : startRecording}
                  className={`record-btn ${isRecording ? 'recording' : ''}`}
                  disabled={loading}
                >
                  <Mic className="btn-icon" />
                  {isRecording ? 'Stop Recording' : 'Start Recording'}
                </Button>
                <Button
                  data-testid="upload-button"
                  onClick={() => fileInputRef.current?.click()}
                  variant="outline"
                  className="upload-btn"
                  disabled={loading}
                >
                  <Upload className="btn-icon" />
                  Upload Audio
                </Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="audio/*"
                  onChange={handleFileUpload}
                  style={{ display: 'none' }}
                  data-testid="audio-file-input"
                />
              </div>
              {audioBlob && (
                <div className="audio-status" data-testid="audio-ready-indicator">
                  <Badge className="audio-badge">Audio Ready</Badge>
                </div>
              )}
              <Button
                data-testid="transcribe-button"
                onClick={transcribeAudio}
                className="action-btn"
                disabled={!audioBlob || loading}
              >
                {loading ? <Loader2 className="btn-icon animate-spin" /> : null}
                Transcribe Audio
              </Button>
            </CardContent>
          </Card>

          {/* Transcript Section */}
          <Card className="card" data-testid="transcript-card">
            <CardHeader>
              <CardTitle className="card-title">Transcript</CardTitle>
            </CardHeader>
            <CardContent>
              <Textarea
                data-testid="transcript-textarea"
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                placeholder="Audio transcript will appear here..."
                className="transcript-area"
                rows={8}
              />
            </CardContent>
          </Card>

          {/* Non-Verbal Actions */}
          <Card className="card" data-testid="non-verbal-card">
            <CardHeader>
              <CardTitle className="card-title">Observed Non-Verbal Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="action-grid">
                {NON_VERBAL_OPTIONS.map((action) => (
                  <Button
                    key={action}
                    data-testid={`action-${action.toLowerCase().replace(/\s+/g, '-')}`}
                    onClick={() => toggleAction(action)}
                    variant={selectedActions.includes(action) ? 'default' : 'outline'}
                    className="action-chip"
                  >
                    {action}
                  </Button>
                ))}
              </div>
              <div className="custom-action-input">
                <input
                  data-testid="custom-action-input"
                  type="text"
                  value={customAction}
                  onChange={(e) => setCustomAction(e.target.value)}
                  placeholder="Add custom observation..."
                  className="custom-input"
                  onKeyPress={(e) => e.key === 'Enter' && addCustomAction()}
                />
                <Button
                  data-testid="add-custom-action-button"
                  onClick={addCustomAction}
                  size="sm"
                  className="add-btn"
                >
                  <Plus className="btn-icon" />
                </Button>
              </div>
              {selectedActions.length > 0 && (
                <div className="selected-actions" data-testid="selected-actions-list">
                  {selectedActions.map((action, idx) => (
                    <Badge key={idx} className="selected-badge" data-testid={`selected-action-${idx}`}>
                      {action}
                      <X
                        className="remove-icon"
                        onClick={() => toggleAction(action)}
                        data-testid={`remove-action-${idx}`}
                      />
                    </Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Action Buttons */}
          <Card className="card action-card" data-testid="action-buttons-card">
            <CardContent className="action-card-content">
              <Button
                data-testid="generate-notes-button"
                onClick={generateNotes}
                className="generate-btn"
                disabled={!transcript || loading}
              >
                {loading ? <Loader2 className="btn-icon animate-spin" /> : null}
                Generate Notes
              </Button>
              <Button
                data-testid="clear-all-button"
                onClick={clearAll}
                variant="outline"
                className="clear-btn"
              >
                Clear All
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Clinical Output */}
        {clinicalData && (
          <div className="clinical-output" data-testid="clinical-output-section">
            <h2 className="output-title">Clinical Documentation</h2>
            <div className="output-grid">
              <Card className="output-card" data-testid="subjective-card">
                <CardHeader>
                  <CardTitle className="output-card-title">Subjective</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="output-text" data-testid="subjective-text">{clinicalData.subjective}</p>
                </CardContent>
              </Card>

              <Card className="output-card" data-testid="objective-card">
                <CardHeader>
                  <CardTitle className="output-card-title">Objective</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="output-text" data-testid="objective-text">{clinicalData.objective}</p>
                </CardContent>
              </Card>

              <Card className="output-card" data-testid="assessment-card">
                <CardHeader>
                  <CardTitle className="output-card-title">Assessment</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="output-text" data-testid="assessment-text">{clinicalData.assessment}</p>
                </CardContent>
              </Card>

              <Card className="output-card" data-testid="plan-card">
                <CardHeader>
                  <CardTitle className="output-card-title">Plan</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="output-text" data-testid="plan-text">{clinicalData.plan}</p>
                </CardContent>
              </Card>

              <Card className="output-card" data-testid="icd10-card">
                <CardHeader>
                  <CardTitle className="output-card-title">ICD-10 Codes</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2" data-testid="icd10-codes-list">
                    {clinicalData.icd10_codes?.map((item, idx) => (
                      <div key={idx} className="code-item" data-testid={`icd10-code-${idx}`}>
                        <Badge className="code-badge">{item.code}</Badge>
                        <span className="code-text">{item.condition}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card className="output-card" data-testid="drug-interactions-card">
                <CardHeader>
                  <CardTitle className="output-card-title">Drug Interaction Alerts</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3" data-testid="drug-interactions-list">
                    {clinicalData.medication_interactions?.length > 0 ? (
                      clinicalData.medication_interactions.map((item, idx) => (
                        <div key={idx} className="interaction-item" data-testid={`drug-interaction-${idx}`}>
                          <div className="interaction-header">
                            <AlertCircle className="interaction-icon" />
                            <Badge variant="destructive" className="severity-badge">
                              {item.severity}
                            </Badge>
                          </div>
                          <p className="interaction-drugs">
                            {item.drug_a} + {item.drug_b}
                          </p>
                          <p className="interaction-note">{item.note}</p>
                        </div>
                      ))
                    ) : (
                      <p className="no-data" data-testid="no-drug-interactions">No interactions detected</p>
                    )}
                  </div>
                </CardContent>
              </Card>

              <Card className="output-card" data-testid="red-flags-card">
                <CardHeader>
                  <CardTitle className="output-card-title">Red Flags</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2" data-testid="red-flags-list">
                    {clinicalData.red_flags?.length > 0 ? (
                      clinicalData.red_flags.map((flag, idx) => (
                        <div key={idx} className="red-flag-item" data-testid={`red-flag-${idx}`}>
                          <AlertCircle className="flag-icon" />
                          <span>{flag}</span>
                        </div>
                      ))
                    ) : (
                      <p className="no-data" data-testid="no-red-flags">No red flags identified</p>
                    )}
                  </div>
                </CardContent>
              </Card>

              <Card className="output-card summary-card" data-testid="clinical-summary-card">
                <CardHeader>
                  <CardTitle className="output-card-title">Clinical Summary</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="summary-text" data-testid="clinical-summary-text">{clinicalData.clinical_summary}</p>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;