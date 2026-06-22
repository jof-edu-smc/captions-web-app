import { useEffect, useMemo, useState } from 'react';

const AGE_OPTIONS = ['17 and younger', '18 - 24', '25 - 49', '50 - 64', '65 and older'];
const AUDIO_OPTIONS = ['None', '0 - 1', '1 - 5', '5 - 10', '10+'];
const HEARING_OPTIONS = ['No', 'Yes'];

const PHASE_LABELS = {
  step_1: 'Step 1',
  step_2: 'Step 2',
  step_3: 'Step 3',
};

const NEXT_PHASE = {
  step_1: 'step_2',
  step_2: 'step_3',
  step_3: 'completion',
};

function parseQueryParams() {
  const params = new URLSearchParams(window.location.search);
  
  // 1. Attempt to grab the Prolific-injected session ID first
  let sessionId = params.get('session_id');

  // 2. Fallback for local testing or non-Prolific traffic
  if (!sessionId) {
    // Check if we already generated one for this specific browser tab
    sessionId = sessionStorage.getItem('local_session_id');
    
    // If not, generate a brand new UUID and save it to the browser
    if (!sessionId) {
      sessionId = crypto.randomUUID(); 
      sessionStorage.setItem('local_session_id', sessionId);
    }
  }

  // 3. Provide safe fallback strings for the other IDs so the database doesn't log blanks
  return {
    prolific_id: params.get('prolific_id') || `local_user_${crypto.randomUUID().slice(0, 8)}`,
    study_id: params.get('study_id') || 'pilot_study_participant',
    session_id: sessionId,
    completion_url: params.get('completion_url') || params.get('redirect_url') || '',
    completion_code: params.get('completion_code') || '',
  };
}

function buildCompletionUrl(context) {
  if (context.completion_url) {
    return context.completion_url;
  }
  if (context.completion_code) {
    return `https://app.prolific.com/submissions/complete?cc=${encodeURIComponent(context.completion_code)}`;
  }
  return '';
}

function logToServer(level, message, context = {}) {
  fetch('/api/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level, message, context }),
  }).catch((err) => {
    // Silently fail if the logger itself fails, so we don't crash the app
    console.error("Failed to send log to server:", err);
  });
}

function ChipGroup({ label, options, value, onChange, hint }) {
  return (
    <section className="field-group">
      <div className="field-heading">
        <h2>{label}</h2>
        {hint ? <p>{hint}</p> : null}
      </div>
      <div className="chip-row" role="radiogroup" aria-label={label}>
        {options.map((option) => (
          <button
            key={option}
            type="button"
            className={`chip ${value === option ? 'chip-active' : ''}`}
            onClick={() => onChange(option)}
            aria-pressed={value === option}
          >
            {option}
          </button>
        ))}
      </div>
    </section>
  );
}

function LikertScale({ value, onChange, name, ariaLabel, lowLabel, middleLabel, highLabel }) {
  const labels = ['1', '2', '3', '4']; // Set to 4 because of Lipping Et al. 

  return (
    <div className="likert-shell">
      <div className="likert-scale" role="radiogroup" aria-label={ariaLabel}>
        {labels.map((label) => (
          <label key={label} className={`likert-option ${value === label ? 'likert-option-active' : ''}`}>
            <input
              type="radio"
              name={name}
              value={label}
              checked={value === label}
              onChange={() => onChange(label)}
            />
            <span>{label}</span>
          </label>
        ))}
      </div>
      <div className="likert-labels">
        <span style={{ gridColumn: 1 }}>{lowLabel}</span>
        {/* Force the high label into the 4th slot so it aligns perfectly */}
        <span style={{ gridColumn: 4 }}>{highLabel}</span> 
      </div>
    </div>
  );
}

function GrammarScale({ value, onChange }) {
  return (
    <LikertScale
      value={value}
      onChange={onChange}
      name="grammar"
      ariaLabel="Grammar correctness rating"
      lowLabel="Bad"
      middleLabel="OK"
      highLabel="Good"
    />
  );
}

function AccuracyScale({ value, onChange }) {
  return (
    <LikertScale
      value={value}
      onChange={onChange}
      name="accuracy"
      ariaLabel="Accuracy of the description rating"
      lowLabel="Bad"
      middleLabel="OK"
      highLabel="Good"
    />
  );
}

function ScreenShell({ eyebrow, title, description, children, footer }) {
  return (
    <main className="screen-shell">
      <div className="screen-card">
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {description ? <p className="screen-description">{description}</p> : null}
        {children}
        {footer ? <div className="card-footer">{footer}</div> : null}
      </div>
    </main>
  );
}

function AudioBlock({ trial, caption, baseline, showCaption = false, showBaseline = false }) {
  // Gracefully handle undefined trials during loading states
  if (!trial) return null;

  return (
    <section className="trial-block stack">
      <div className="audio-players-grid" style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '16px' }}>
        
        {trial.speech_file_url && (
          <div className="audio-row">
            <span className="caption-label">A human voice in the space</span>
            <audio 
              controls preload="none" 
              src={trial.speech_file_url} 
              className="audio-player"
              style={{ width: '100%' }} 
              onStalled={() => logToServer('WARN', 'Audio playback stalled (likely Chrome limit)', { url: trial.speech_file_url })}
              onError={(e) => logToServer('ERROR', 'Audio failed to load completely', { error: e.nativeEvent.type, url: trial.speech_file_url })}
            />
          </div>
        )}

        {trial.music_file_url && (
          <div className="audio-row">
            <span className="caption-label">A musical instrument in the space</span>
            <audio 
              controls 
              preload="none" 
              src={trial.music_file_url} 
              className="audio-player" 
              style={{ width: '100%' }} 
              onStalled={() => logToServer('WARN', 'Audio playback stalled (likely Chrome limit)', { url: trial.speech_file_url })}
              onError={(e) => logToServer('ERROR', 'Audio failed to load completely', { error: e.nativeEvent.type, url: trial.speech_file_url })}
            />
          </div>
        )}

        {trial.clap_file_url && (
          <div className="audio-row">
            <span className="caption-label">A clap or pop in the space</span>
            <audio 
              controls 
              preload="none" 
              src={trial.clap_file_url} 
              className="audio-player" 
              style={{ width: '100%' }}
              onStalled={() => logToServer('WARN', 'Audio playback stalled (likely Chrome limit)', { url: trial.speech_file_url })}
              onError={(e) => logToServer('ERROR', 'Audio failed to load completely', { error: e.nativeEvent.type, url: trial.speech_file_url })}
            />
          </div>
        )}

      </div>

      {showCaption && caption ? (
        <div className="caption-box">
          <span className="caption-label">Caption</span>
          <p>{caption}</p>
        </div>
      ) : null}
      
      {showBaseline && baseline ? (
        <div className="caption-box caption-box-muted">
          <span className="caption-label">Baseline caption</span>
          <p>{baseline}</p>
        </div>
      ) : null}
    </section>
  );
}

function IntroScreen({ completionUrl, pisUrl, cfUrl, onContinue }) {
  return (
    <ScreenShell
      eyebrow="Welcome"
      title="Acoustic Caption Survey"
      description="Please download & read the Participant Information Sheet and Consent Sheet informing what you consent to by taking part in the study."
      footer={
        <button className="primary-button" type="button" onClick={onContinue} disabled={!pisUrl}>
          Consent & Proceed
        </button>
      }
    >
      {/* <label className="text-area-shell">
        <span className="caption-label">Create Caption</span> */}
      <div className="intro-grid">
        <label className="text-area-shell">
          <span><b>By clicking "Consent & Proceed" you agree and understand the points in the Consent Form and Participant Information Sheet.</b></span>
          <span>Additionally, please <b>turn off any VPN</b> temporarily should you proceed with the survey.</span>
        </label>
        {pisUrl ? (
          <a className="secondary-link" href={pisUrl} target="_blank" rel="noreferrer">
            Open Participant Information Sheet (PDF)
          </a>
        ) : (
          <span className="context-note">Loading Participant Information to Download...</span>
        )}
        {cfUrl ? (
          <a className="secondary-link" href={cfUrl} target="_blank" rel="noreferrer">
            Open Consent Sheet (PDF)
          </a>
        ) : (
          <span className="context-note">Loading Consent Sheet to Download...</span>
        )}
        {completionUrl ? <p className="context-note">Prolific completion link detected and will be used at the end of the study.</p> : null}
      </div>
    </ScreenShell>
  );
}

function DemographicsScreen({ demographics, onChange, onSubmit }) {
  const canContinue = Boolean(demographics.age_range && demographics.experience_in_audio);

  return (
    <ScreenShell
      eyebrow="Participant profile"
      title="Demographics Form"
      description="Select your age range and your experience in audio-related work. Participants aged 17 and younger cannot proceed."
      footer={
        <button className="primary-button" type="button" onClick={onSubmit} disabled={!canContinue}>
          Next
        </button>
      }
    >
      <div className="stack">
        <ChipGroup
          label="Age Range"
          options={AGE_OPTIONS}
          value={demographics.age_range}
          onChange={(value) => onChange({ ...demographics, age_range: value })}
          hint="Choose the range that best matches your current age."
        />
        <ChipGroup
          label="Experience in Audio"
          options={AUDIO_OPTIONS}
          value={demographics.experience_in_audio}
          onChange={(value) => onChange({ ...demographics, experience_in_audio: value })}
          hint="Estimate how much audio-related experience you have."
        />
        <ChipGroup
          label="Hearing"
          options={HEARING_OPTIONS}
          value={demographics.hearing}
          onChange={(value) => onChange({ ...demographics, hearing: value })}
          hint="Do you have any hearing impairments or conditions that might affect your ability to hear audio clearly?"
        />
      </div>
    </ScreenShell>
  );
}

function BlockedScreen() {
  return (
    <ScreenShell
      eyebrow="Ineligible"
      title="You cannot legally proceed with this survey"
      description="Because your selected age range is 17 and younger, the study must stop here. Please close this tab and return to Prolific."
    />
  );
}

function CompletionScreen({ completionUrl }) {
  useEffect(() => {
    if (!completionUrl) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      window.location.assign(completionUrl);
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [completionUrl]);
  console.log("Completion URL:", completionUrl);
  if (completionUrl === null || completionUrl === undefined || completionUrl === '') {
    return (
      <ScreenShell
        eyebrow="Completion"
        title="Thank you for participating"
        description="You have finished all three evaluation steps and the study is complete. Thank you so much for your time and effort."
      />
    );
  }
  else {
    return (
      <ScreenShell
        eyebrow="Complete"
        title="Thank you for participating"
        description="You have finished all three evaluation steps and the study is complete. Thank you so much for your time and effort. Please use the Prolific completion link below if it has not redirected automatically."
        footer={
          completionUrl ? (
            <a className="primary-button primary-button-link" href={completionUrl}>
              Continue to Prolific
            </a>
          ) : null
        }
      />
    );
  }
}

function Step1Screen({ trial, phaseIndex, totalTrials, onSubmit, submitting }) {
  const [text, setText] = useState('');

  useEffect(() => {
    setText('');
  }, [trial?.trial_index]);

  if (!trial) {
    return null;
  }

  const remaining = 250 - text.length;

  return (
    <ScreenShell
      eyebrow={`${PHASE_LABELS.step_1} · ${phaseIndex + 1}/${totalTrials}`}
      title="Write an Original Caption"
      description="Listen to the separate recordings of three different sources in the same physical space. Write a new caption from scratch that describes the acoustics of the space they are in. Keep it under 250 characters. "
      footer={
        <button className="primary-button" type="button" onClick={() => onSubmit(text)} disabled={!text.trim() || submitting}>
          Submit &amp; Next
        </button>
      }
    >
      <AudioBlock trial={trial} />
      <label className="text-area-shell">
        <span className="caption-label">Create Caption</span>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value.slice(0, 250))}
          rows={3}
          maxLength={250}
          placeholder="Type your caption here..."
        />
      </label>
      <div className="countdown">{remaining} characters remaining</div>
    </ScreenShell>
  );
}

function Step2Screen({ trial, phaseIndex, totalTrials, onSubmit, submitting }) {
  const baseline = trial?.baseline_caption;
  const [text, setText] = useState(baseline);

  useEffect(() => {
    setText(baseline || '');
  }, [trial?.trial_index]);

  if (!trial) {
    return null;  
  }

  return (
    <ScreenShell
      eyebrow={`${PHASE_LABELS.step_2} · ${phaseIndex + 1}/${totalTrials}`}
      title="Rephrasing / Editing already made Captions"
      description="Edit the provided caption if you want to improve it, or leave it unchanged and submit to accept it."
      footer={
        <button className="primary-button" type="button" onClick={() => onSubmit(text)} disabled={!text.trim() || submitting}>
          Submit &amp; Next
        </button>
      }
    >
      <AudioBlock trial={trial} baseline={baseline} showBaseline />
      <label className="text-area-shell" padding_top="5px">
        <span className="caption-label">Edit the caption</span>
        <textarea value={text} onChange={(event) => setText(event.target.value)} rows={3} />
      </label>
    </ScreenShell>
  );
}

function Step3Screen({ trial, phaseIndex, totalTrials, onSubmit, submitting }) {
  const [grammarRating, setGrammarRating] = useState('');
  const [accuracyRating, setAccuracyRating] = useState('');

  useEffect(() => {
    setGrammarRating('');
    setAccuracyRating('');
  }, [trial?.trial_index]);

  if (!trial) {
    return null;
  }

  const canSubmit = Boolean(grammarRating && accuracyRating && !submitting);
  
  return (
    <ScreenShell
      eyebrow={`${PHASE_LABELS.step_3} · ${phaseIndex + 1}/${totalTrials}`}
      title="Grammar and Accuracy Ratings"
      description="Rate the caption on grammar correctness and how accurately it describes the acoustics."
      footer={
        <button className="primary-button" type="button" onClick={() => onSubmit(grammarRating, accuracyRating)} disabled={!canSubmit}>
          Submit & Next
        </button>
      }
    >
      <AudioBlock trial={trial} baseline={trial.baseline_caption} showBaseline />
      <section className="stack">
        <div className="field-group">
          <div className="field-heading">
            <h2>Grammar Correctness</h2>
            <p>Rate the grammar of the caption.</p>
          </div>
          <GrammarScale value={grammarRating} onChange={setGrammarRating} />
        </div>
        <div className="field-group">
          <div className="field-heading">
            <h2>Accuracy of the Description</h2>
            <p>How accurately does the caption describe the space the performances are located in?</p>
          </div>
          <AccuracyScale value={accuracyRating} onChange={setAccuracyRating} />
        </div>
      </section>
    </ScreenShell>
  );
}

function HeadphoneAdjustmentScreen({ trial, onSubmit, onGoBack }) {
  return (
    <ScreenShell
      eyebrow="Headphone Calibration"
      title="Adjust Headphone Volume"
      description="Starting with your headphone volume at a low level, listen to all three references and adjust your headphone volume to a comfortable but clear level. Play the files as many times as you like."
      footer={
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', width: '100%' }}>
          <button 
            type="button" 
            onClick={onGoBack} 
            style={{ 
              background: 'transparent', 
              border: '2px solid var(--accent)', 
              color: 'var(--accent)', 
              padding: '0 22px', 
              borderRadius: '999px', 
              cursor: 'pointer', 
              fontWeight: '700' 
            }}
          >
            Back
          </button>
          <button className="primary-button" type="button" onClick={onSubmit}>
            Start Training Exercises
          </button>
        </div>
      }
    >
      <AudioBlock trial={{ 
        speech_file_url: trial?.speech_file_url,  
        music_file_url: trial?.music_file_url,
        clap_file_url: trial?.clap_file_url
      }} />
    </ScreenShell>
  );
}

function TrainingStep1Screen({ trial, onSubmit, onGoBack }) {
  const [text, setText] = useState('');
  const remaining = 250 - text.length;
  const baseline = trial?.training_baseline_caption;

  if (!trial) {
    return null;
  }
  else {
    return (
      <ScreenShell
        eyebrow="Training · Step 1"
        title="Practice: Generative Captioning"
        description="In this step you must describe the acoustics of the space that the three different sources are in. Listen to all 3 three sources (located in the same room), then describe the space in your own words. Feel free to be creative and elaborate on specific nuances that you hear. NOTE: This is a practice screen, and the response is not saved; don't spend too much time on this page. Just try to get a feel for the task and move on to the next page."
        footer={
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', width: '100%' }}>
            <button 
              type="button" 
              onClick={onGoBack} 
              style={{ 
                background: 'transparent', 
                border: '2px solid var(--accent)', 
                color: 'var(--accent)', 
                padding: '0 22px', 
                borderRadius: '999px', 
                cursor: 'pointer', 
                fontWeight: '700' 
              }}
            >
              Back
            </button>
            <button className="primary-button" type="button" onClick={onSubmit} disabled={!text.trim()}>
              Continue
            </button>
          </div>
        }
      >
        <AudioBlock trial={{ 
          speech_file_url: trial?.speech_file_url,  
          music_file_url: trial?.music_file_url,
          clap_file_url: trial?.clap_file_url
        }} />
        
        <div className="caption-box caption-box-muted" style={{ marginBottom: '10px' }}>
          <span className="caption-label">Training: Examples of Captions</span>
          <ul style={{ margin: '8px 0 0 0', paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <li>The room sounds very bright. The high frequencies are significantly accented, especially for the snare and cymbals. The late reverb tail is quite interesting -- There is a nice richness to it. The room feels to be large and spacious. The top of the space could have a dome like structure, producing a lush reverb.</li>
            <li>The room feels uncomfortably small, a bit claustrophobic. The early reflections are very audible, indicating closely spaced walls. The room is coloured with a non-uniform frequency response.</li>
            <li>Reflections are short and controlled, creating an intimate and close acoustic feel characteristic of a compact or well-damped room.</li>
          </ul>
        </div>

        <label className="text-area-shell">
          <span className="caption-label">Practice caption</span>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value.slice(0, 200))}
            rows={6}
            maxLength={200}
            placeholder="Type a practice caption here..."
          />
        </label>
        <div className="countdown">{remaining} characters remaining</div>
      </ScreenShell>
    );
  }
  
}

function TrainingStep2Screen({ trial, onSubmit, onGoBack }) {
  const baseline = trial?.training_baseline_caption;
  const [text, setText] = useState(baseline);

  if (!trial) {
    return null;
  }
  return (
    <ScreenShell
      eyebrow="Training · Step 2"
      title="Practice: Rephrasing / Editing"
      description="In the second phase of this study, we will ask you to listen to those three audio clips, read a caption and make any corrections IF necessary. If you find that the caption provided as a baseline is in fact perfect. Then you can click the Next button and move on to the next sample in the survey."
      footer={
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', width: '100%' }}>
          <button 
            type="button" 
            onClick={onGoBack} 
            style={{ 
              background: 'transparent', 
              border: '2px solid var(--accent)', 
              color: 'var(--accent)', 
              padding: '0 22px', 
              borderRadius: '999px', 
              cursor: 'pointer', 
              fontWeight: '700' 
            }}
          >
            Back to Step 1
          </button>
          <button className="primary-button" type="button" onClick={onSubmit} disabled={!text.trim()}>
            Continue
          </button>
        </div>
      }
    >
      
      <AudioBlock trial={{ 
          speech_file_url: trial?.speech_file_url,  
          music_file_url: trial?.music_file_url,
          clap_file_url: trial?.clap_file_url
        }} baseline={baseline} showBaseline />
      
      <label className="text-area-shell" style={{ paddingTop: '5px' }}>
        <span className="caption-label">Edit the caption</span>
        <textarea value={text} onChange={(event) => setText(event.target.value)} rows={2} />
      </label>
    </ScreenShell>
  );
}

function TrainingCompleteScreen({ onProceed, onGoBack }) {
  return (
    <ScreenShell
      eyebrow="Training Complete"
      title="Ready to begin the actual survey?"
      description="You have finished the practice rounds. The next screens will use the real audio dataset, and your responses will be recorded. Are you sure you are ready to proceed?"
      footer={
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', width: '100%' }}>
          <button 
            type="button" 
            onClick={onGoBack} 
            style={{ 
              background: 'transparent', 
              border: '2px solid var(--accent)', 
              color: 'var(--accent)', 
              padding: '0 22px', 
              borderRadius: '999px', 
              cursor: 'pointer', 
              fontWeight: '700' 
            }}
          >
            Wait, let me review
          </button>
          <button className="primary-button" type="button" onClick={onProceed}>
            Yes, start actual survey
          </button>
        </div>
      }
    />
  );
}

export default function App() {
  const prolificContext = useMemo(() => parseQueryParams(), []);
  const completionUrl = useMemo(() => buildCompletionUrl(prolificContext), [prolificContext]);
  const [phase, setPhase] = useState('loading');
  const [stimuli, setStimuli] = useState(null);
  const [training, setTraining] = useState(null);
  const [pisUrl, setPisUrl] = useState('');
  const [cfUrl, setCfUrl] = useState('');
  const [demographics, setDemographics] = useState({ age_range: '', experience_in_audio: '', hearing: '' });
  const [trialIndex, setTrialIndex] = useState({ 
      training_step_1: 0,
      training_step_2: 0,
      step_1: 0, 
      step_2: 0, 
      step_3: 0
  });
  const [statusMessage, setStatusMessage] = useState('Creating User Study');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function loadStimuli() {
      try {
        const params = new URLSearchParams({
          prolific_id: prolificContext.prolific_id,
          study_id: prolificContext.study_id,
          session_id: prolificContext.session_id,
          seed: [prolificContext.prolific_id, prolificContext.study_id, prolificContext.session_id].filter(Boolean).join(':'),
        });
        
        const response = await fetch(`/api/get-stimuli?${params.toString()}`);
        if (!response.ok) {
          throw new Error(`Stimulus request failed with status ${response.status}`);
        }
        const data = await response.json();
        setStatusMessage('Gathering Audio Files.')
        setStimuli(data.stimuli);
        setStatusMessage('Setting up Training Steps')
        setTraining(data.training);
        setStatusMessage('Fetching Participant Information Sheet')
        setPisUrl(data.pis_url);
        setCfUrl(data.cf_url);
        setStatusMessage('Survey ready.');
        
        logToServer('INFO', 'Session successfully loaded and ready', { 
          session_id: prolificContext.session_id, 
          prolific_id: prolificContext.prolific_id 
        });

        setPhase('intro');
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Failed to load stimuli.';
        setStatusMessage(errorMsg);
        logToServer('ERROR', 'Failed to load stimuli', { 
          session_id: prolificContext.session_id,
          error: errorMsg 
        });
      }
    }

    loadStimuli();
  }, [prolificContext]);

  async function submitPhaseResponse(phaseName, stimulus, payload) {
    setSubmitting(true);
    try {
      const response = await fetch('/api/submit-response', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          phase: phaseName,
          trial_index: stimulus?.trial_index ?? 0,
          participant_context: {
            ...prolificContext,
            ...demographics,
          },
          stimulus,
          ...payload,
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Submit failed with status ${response.status}`);
      }
    } catch(error) {
      const errorMsg = error instanceof Error ? error.message : 'Failed to submit response.';
      setStatusMessage(errorMsg);
      logToServer('ERROR', 'Failed to submit response', { 
        session_id: prolificContext.session_id,
        error: errorMsg 
      });
    } finally {
      setSubmitting(false);
    }
  }

  const step1Trials = stimuli?.step_1 || [];
  const step2Trials = stimuli?.step_2 || [];
  const step3Trials = stimuli?.step_3 || [];

  if (statusMessage.startsWith('Stimulus request failed') || statusMessage.startsWith('Failed to load')) {
    return (
      <ScreenShell eyebrow="Error" title="Unable to start the survey" description={statusMessage} />
    );
  }

  if (phase === 'intro') {
    return (
      <IntroScreen
        completionUrl={completionUrl}
        pisUrl={pisUrl} 
        cfUrl={cfUrl}
        onContinue={() => setPhase('demographics')}
      />
    );
  }

  if (phase === 'demographics') {
    return (
      <DemographicsScreen
        demographics={demographics}
        onChange={setDemographics}
        onSubmit={() => {
          if (demographics.age_range === '17 and younger') {
            setPhase('blocked');
            return;
          }
          // Redirect to calibration instead of training
          setPhase('headphone_calibration'); 
        }}
      />
    );
  }

  if (phase === 'headphone_calibration') {
    const trial = training?.training_step_1;
    return (
      <HeadphoneAdjustmentScreen 
        trial={trial}
        onSubmit={() => setPhase('training_step_1')} 
        onGoBack={() => setPhase('demographics')} 
      />
    );
  }

  if (phase === 'blocked') {
    return <BlockedScreen />;
  }

  if (phase === 'training_step_1') {
    const trial = training?.training_step_1;
    const step_1 = step1Trials[trialIndex.step_1];
    if (!step_1) {
      setPhase('training_step_2');
      return null; // Prevent rendering the next screen until the phase is updated
      // return (
      //   <ScreenShell
      //     eyebrow="Phase Skipped"
      //     title="No Editing Trials Available"
      //     description="There are currently no captions in the database that require editing."
      //     footer={
      //       <button className="primary-button" onClick={() => setPhase('training_step_2')}>
      //         Continue
      //       </button>
      //     }
      //   />
      // );
    }
    return (
      <TrainingStep1Screen 
        trial={trial}
        onSubmit={() => setPhase('training_step_2')}
        onGoBack={() => setPhase('headphone_calibration')} 
      />
    );
  }

  if (phase === 'training_step_2') {
    const trial = training?.training_step_2;
    const step_2 = step2Trials[trialIndex.step_2];
    if (!step_2) {
      setPhase('training_complete');
      return null; // Prevent rendering the next screen until the phase is updated
      // return (
      //   <ScreenShell
      //     eyebrow="Phase Skipped"
      //     title="No Editing Trials Available"
      //     description="There are currently no captions in the database that require editing."
      //     footer={
      //       <button className="primary-button" onClick={() => setPhase('training_complete')}>
      //         Continue
      //       </button>
      //     }
      //   />
      // );
    }
    return (
      <TrainingStep2Screen 
        trial={trial}
        onSubmit={() => setPhase('training_complete')} 
        onGoBack={() => setPhase('training_step_1')} // Returns the user to practice step 1
      />
    );
  }

  if (phase === 'training_complete') {
    if (!step1Trials.length & !step2Trials.length) {
      setPhase('step_1');
      return null;
    }
    return (
      <TrainingCompleteScreen 
        onProceed={() => setPhase('step_1')} 
        onGoBack={() => setPhase('training_step_2')} 
      />
    );
  }

  if (phase === 'step_1') {
    const trial = step1Trials[trialIndex.step_1];
    return (
      <Step1Screen
        trial={trial}
        phaseIndex={trialIndex.step_1}
        totalTrials={step1Trials.length}
        submitting={submitting}
        onSubmit={async (generatedText) => {
          if (!trial || !generatedText.trim()) {
            return;
          }

          logToServer('INFO', 'Session successfully loaded and ready', { 
            generated_text: generatedText,
            raw_text: generatedText,
            response_text: generatedText,
          });

          await submitPhaseResponse('step_1', trial, {
            generated_text: generatedText,
            raw_text: generatedText,
            response_text: generatedText,
          });

          const nextIndex = trialIndex.step_1 + 1;
          if (nextIndex >= step1Trials.length) {
            setPhase(NEXT_PHASE.step_1);
            setTrialIndex((current) => ({ ...current, step_1: 0 }));
          } else {
            setTrialIndex((current) => ({ ...current, step_1: nextIndex }));
          }
        }}
      />
    );
  }

  if (phase === 'step_2') {
    const trial = step2Trials[trialIndex.step_2];
    console.log("Current Step 2 Trial:", trial);

    if (!trial) {
      const nextIndex = trialIndex.step_2 + 1;
      if (nextIndex >= step2Trials.length) {
        setPhase(NEXT_PHASE.step_2);
        setTrialIndex((current) => ({ ...current, step_2: 0 }));
      } else {
        setTrialIndex((current) => ({ ...current, step_2: nextIndex }));
      }
      return null; 
    }

    return (
      <Step2Screen
        trial={trial}
        phaseIndex={trialIndex.step_2}
        totalTrials={step2Trials.length}
        submitting={submitting}
        onSubmit={async (editedText) => {
          if (!trial) {
            return;
          }
          await submitPhaseResponse('step_2', trial, {
            caption_id: trial.caption_id, // <-- Explicitly bind the ID
            edited_text: editedText,
            response_text: editedText,
          });
          const nextIndex = trialIndex.step_2 + 1;
          if (nextIndex >= step2Trials.length) {
            setPhase(NEXT_PHASE.step_2);
            setTrialIndex((current) => ({ ...current, step_2: 0 }));
          } else {
            setTrialIndex((current) => ({ ...current, step_2: nextIndex }));
          }
        }}
      />
    );
  }

  if (phase === 'step_3') {
    const trial = step3Trials[trialIndex.step_3];
    console.log("Current Step 3 Trial:", trial);

    if (!trial) {
      const nextIndex = trialIndex.step_3 + 1;
      if (nextIndex >= step3Trials.length) {
        setPhase(NEXT_PHASE.step_3);
      } else {
        setTrialIndex((current) => ({ ...current, step_3: nextIndex }));
      }
      return null;
    }
    
    return (
      <Step3Screen
        trial={trial}
        phaseIndex={trialIndex.step_3}
        totalTrials={step3Trials.length}
        submitting={submitting}
        onSubmit={async (grammarRating, accuracyRating) => {
          if (!trial || !grammarRating || !accuracyRating) {
            return;
          }
          await submitPhaseResponse('step_3', trial, {
            caption_id: trial.caption_id,
            grammar_rating: grammarRating,
            accuracy_rating: accuracyRating,
          });
          const nextIndex = trialIndex.step_3 + 1;
          if (nextIndex >= step3Trials.length) {
            setPhase(NEXT_PHASE.step_3);
          } else {
            setTrialIndex((current) => ({ ...current, step_3: nextIndex }));
          }
        }}
      />
    );
  }

  if (phase === 'completion') {
    logToServer('INFO', 'A study has been completed', { 
          session_id: prolificContext.session_id
        });
    return <CompletionScreen completionUrl={completionUrl} />;
  }

  return <ScreenShell eyebrow="Loading" title="Preparing study" description={statusMessage}>
    <div style={{ display: 'flex', justifyContent: 'center', margin: '40px 0 20px 0' }}>
        <div className="loader"></div>
      </div>
  </ScreenShell>;
}