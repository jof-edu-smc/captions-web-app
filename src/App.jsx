import { useEffect, useMemo, useState } from 'react';

const AGE_OPTIONS = ['17 and younger', '18 - 24', '25 - 49', '50 - 64', '65 and older'];
const AUDIO_OPTIONS = ['None', '0 - 1', '1 - 5', '5 - 10', '10+'];
const HEARING_OPTIONS = ['No', 'Yes'];

const PHASE_LABELS = {
  step_3: 'Step 3',
};

const NEXT_PHASE = {
  step_3: 'completion',
};

const STEP_PHASES = ['step_3'];

function getAvailableSteps(trials) {
  return STEP_PHASES.filter((step) => trials[step]?.length > 0);
}

function getNextAvailableStep(currentStep, availableSteps) {
  const currentIndex = availableSteps.indexOf(currentStep);
  return availableSteps[currentIndex + 1] || 'completion';
}

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

// This component is used to display two captions (A and B) for comparison, allowing the user to select which one they prefer. It takes in the current selected value, a callback for when the selection changes, and the two caption texts.
function CaptionAndB({ trial, selectedCaption, onChange }) {
  if (!trial) return null;
  return (
    <div className="caption-shell">
      <div className="caption-box caption-box-muted caption-comparison-context">
          <div className="caption-context-section">
            <h3>Acoustic profile</h3>
            <dl className="acoustic-metadata">
              <div><dt>Location</dt><dd>{trial.metadata?.location || 'Not available'}</dd></div>
              <div><dt>RT60</dt><dd>{trial.metadata?.rt60 || 'Not available'}</dd></div>
              <div><dt>DRR</dt><dd>{trial.metadata?.drr || 'Not available'}</dd></div>
              {/* <div><dt>C50</dt><dd>{trial.metadata?.c50 || 'Not available'}</dd></div>
              <div><dt>C80</dt><dd>{trial.metadata?.c80 || 'Not available'}</dd></div>
              <div><dt>D50</dt><dd>{trial.metadata?.d50 || 'Not available'}</dd></div> */}
            </dl>
            {trial.metadata?.image_link && (
              <img
                src={trial.metadata.image_link}
                alt="Acoustic profile"
                style={{ display: 'block', maxWidth: '100%', height: 'auto', marginTop: '1rem' }}
              />
            )}
          </div>
          
          <div className="caption-context-section">
            <h3>Captions to compare</h3>
            <div className="comparison-captions">
              <div className="comparison-caption">
                <span className="comparison-caption-label">Caption A</span>
                <p>{trial.caption_a_text || 'Not available'}</p>
              </div>
              <div className="comparison-caption">
                <span className="comparison-caption-label">Caption B</span>
                <p>{trial.caption_b_text || 'Not available'}</p>
              </div>
            </div>
          </div>
      </div>
      <div className="caption-scale" role="radiogroup" aria-label="Select the best caption">
        <label className={`caption-option ${selectedCaption === 'A' ? 'caption-option-active' : ''}`} htmlFor="captionA">
          {/* <strong>Caption A</strong>  */}
          <input
            type="radio"
            id="captionA"
            name="captionChoice"
            value="A"
            checked={selectedCaption === 'A'}
            onChange={() => onChange('A')}
          />
          <span><b>Caption A</b></span>
        </label>
        <label className={`caption-option ${selectedCaption === 'B' ? 'caption-option-active' : ''}`} htmlFor="captionB">
          {/* <strong>Caption B</strong>  */}
          <input
            type="radio"
            id="captionB"
            name="captionChoice"
            value="B"
            checked={selectedCaption === 'B'}
            onChange={() => onChange('B')}
          />
          <span><b>Caption B</b></span>
        </label>
        <label className={`caption-option ${selectedCaption === 'Neither' ? 'caption-option-active' : ''}`} htmlFor="captionNeither">
          {/* <strong>Neither</strong>  */}
          <input
            type="radio"
            id="captionNeither"
            name="captionChoice"
            value="Neither"
            checked={selectedCaption === 'Neither'}
            onChange={() => onChange('Neither')}
          />
          <span><b>Neither</b></span>
        </label>
        <label className={`caption-option ${selectedCaption === 'Both' ? 'caption-option-active' : ''}`} htmlFor="captionBoth">
          {/* <strong>Both</strong>  */}
          <input
            type="radio"
            id="captionBoth"
            name="captionChoice"
            value="Both"
            checked={selectedCaption === 'Both'}
            onChange={() => onChange('Both')}
          />
          <span><b>Both</b></span>
        </label>
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

function AccuracyScale({ value, onChange, name }) {
  return (
    <LikertScale
      value={value}
      onChange={onChange}
      name={name}
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

function IntroScreen({ completionUrl, onContinue }) {
  return (
    <ScreenShell
      eyebrow="Welcome"
      title="Acoustic Caption Survey"
      description="This survey asks you to read a description and look at an image of a space then read two captions that describe what the acoustics sound like. You will then select which caption best describes the acoustics of the space. You can also choose neither or both."
      footer={
        <button className="primary-button" type="button" onClick={onContinue}>
          Proceed
        </button>
      }
    >
      {/* <label className="text-area-shell">
        <span className="caption-label">Create Caption</span> */}
      <div className="intro-grid">
        <label className="text-area-shell">
          <span><b>Click Proceed to start the survey.</b></span>
          <span>Additionally, please <b>turn off any VPN</b> temporarily should you proceed with the survey.</span>
        </label>
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
  
  if (completionUrl === null || completionUrl === undefined || completionUrl === '') {
    return (
      <ScreenShell
        eyebrow="Completion"
        title="Thank you for participating"
        description="You have finished the selected steps for your session and the study is complete. Thank you so much for your time and effort."
      />
    );
  }
  else {
    return (
      <ScreenShell
        eyebrow="Complete"
        title="Thank you for participating"
        description="You have finished the selected steps for your session and the study is complete. Thank you so much for your time and effort. Please use the Prolific completion link below if it has not redirected automatically."
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

function Step3Screen({ trial, phaseIndex, totalTrials, onSubmit, submitting }) {
  const [selectAorB, setSelectAorB] = useState('');
  const [accuracyRatingA, setAccuracyRatingA] = useState('');
  const [accuracyRatingB, setAccuracyRatingB] = useState('');

  useEffect(() => {
    setSelectAorB('');
    setAccuracyRatingA('');
    setAccuracyRatingB('');
  }, [trial?.trial_index]);

  if (!trial) {
    return null;
  }

  const canSubmit = Boolean(selectAorB && accuracyRatingA && accuracyRatingB && !submitting);
  
  return (
    <ScreenShell
      eyebrow={`${PHASE_LABELS.step_3} · ${phaseIndex + 1}/${totalTrials}`}
      title="Compare Captions"
      description="Listen to the three audio files below and follow the directions under 'Select Best Caption'"
      footer={
        <button className="primary-button" type="button" onClick={() => onSubmit(selectAorB, accuracyRatingA, accuracyRatingB)} disabled={!canSubmit}>
          Submit & Next
        </button>
      }
    >
      {/* <AudioBlock trial={trial} baseline={trial.baseline_caption} /> */}
      <section className="stack">
        <div className="field-group">
          <div className="field-heading" style={{ marginBottom: '12px' }}>
            <h1>Select the Best Caption</h1>
            <p>Select whether <b>Caption A or B most accurately describes the acoustics of the space</b> by listening to the three audio files you can play below. If <b>none</b> of them effectively describe the acoustics of the space, then <b>select the Neither option</b>. If <b>both</b> of them are equally effective, then <b>select the Both option</b>.</p>
          </div>
          <CaptionAndB trial={trial} selectedCaption={selectAorB} onChange={setSelectAorB} />
          {/* <GrammarScale value={grammarRating} onChange={setGrammarRating} /> */}
        </div>
        {/* <div className="field-group">
          <div className="field-heading">
            <h2>Accuracy of the Description</h2>
            <p>How accurately does the caption describe the space the performances are located in?</p>
          </div>
          <h2>Caption A</h2>
          <AccuracyScale value={accuracyRatingA} onChange={setAccuracyRatingA} name="accuracy-a" />
          <h2>Caption B</h2>
          <AccuracyScale value={accuracyRatingB} onChange={setAccuracyRatingB} name="accuracy-b" />
        </div> */}
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
            Start Survey
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


export default function App() {
  const prolificContext = useMemo(() => parseQueryParams(), []);
  const completionUrl = useMemo(() => buildCompletionUrl(prolificContext), [prolificContext]);
  const [phase, setPhase] = useState('loading');
  const [stimuli, setStimuli] = useState(null);
  const [showAudioFiles, setShowAudioFiles] = useState(true);
  const [demographics, setDemographics] = useState({ age_range: '', experience_in_audio: '', hearing: '' });
  const [trialIndex, setTrialIndex] = useState({
      step_3: 0,
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
        setShowAudioFiles(data.show_audio_files !== false);
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
  
  const step3Trials = stimuli?.step_3 || [];
  const trialsByStep = { step_3: step3Trials };
  const availableSteps = getAvailableSteps(trialsByStep);

  if (statusMessage.startsWith('Stimulus request failed') || statusMessage.startsWith('Failed to load')) {
    return (
      <ScreenShell eyebrow="Error" title="Unable to start the survey" description={statusMessage} />
    );
  }

  if (phase === 'intro') {
    return (
      <IntroScreen
        completionUrl={completionUrl}
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
          setPhase(showAudioFiles ? 'headphone_calibration' : 'step_3');
        }}
      />
    );
  }

  if (phase === 'headphone_calibration') {
    const trial = step3Trials[0] ?? null;
    return (
      <HeadphoneAdjustmentScreen 
        trial={trial}
        onSubmit={() => setPhase('step_3')} 
        onGoBack={() => setPhase('demographics')} 
      />
    );
  }

  if (phase === 'blocked') {
    return <BlockedScreen />;
  }

  if (phase === 'step_3') {
    const trial = step3Trials[trialIndex.step_3];

    if (!trial) {
      return null;
    }
    
    return (
      <Step3Screen
        trial={trial}
        phaseIndex={trialIndex.step_3}
        totalTrials={step3Trials.length}
        submitting={submitting}
        onSubmit={async (selectedCaption, accuracyRatingA, accuracyRatingB) => {
          if (!trial || !selectedCaption || !accuracyRatingA || !accuracyRatingB) {
            return;
          }
          await submitPhaseResponse('step_3', trial, {
            caption_a: trial.caption_a,
            caption_b: trial.caption_b,
            selected_caption: selectedCaption,
            accuracy_score_a: accuracyRatingA,
            accuracy_score_b: accuracyRatingB,
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