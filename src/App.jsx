import { useEffect, useMemo, useState } from 'react';

const AGE_OPTIONS = ['17 and younger', '18 - 24', '25 - 49', '50 - 64', '65 and older'];
const AUDIO_OPTIONS = ['None', '0 - 1', '1 - 5', '5 - 10', '10+'];

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
  return {
    prolific_id: params.get('prolific_id') || '',
    study_id: params.get('study_id') || '',
    session_id: params.get('session_id') || '',
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
  const labels = ['1', '2', '3', '4', '5'];

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
        <span>{lowLabel}</span>
        <span>{middleLabel}</span>
        <span>{highLabel}</span>
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
      lowLabel="Totally Incorrect"
      middleLabel="Average"
      highLabel="Perfect"
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
      lowLabel="Very inaccurate"
      middleLabel="Neutral"
      highLabel="Very accurate"
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

function AudioBlock({ audioUrl, caption, baseline, showCaption = false, showBaseline = false }) {
  
  return (
    <section className="trial-block">
      <audio controls src={audioUrl} className="audio-player" />
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
      description="Please read the participant information sheet before continuing. This study asks you to listen to short audio clips and respond to three different caption tasks."
      footer={
        <button className="primary-button" type="button" onClick={onContinue}>
          Start survey
        </button>
      }
    >
      <div className="intro-grid">
        <a className="secondary-link" href="/files/PIS-Ferraro-V0.2-25-May-2025.pdf" target="_blank" rel="noreferrer">
          Open participant information sheet (PDF)
        </a>
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

  return (
    <ScreenShell
      eyebrow="Complete"
      title="Thank you for participating"
      description="You have finished all three evaluation steps. Please use the Prolific completion link below if it has not redirected automatically."
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

function Step1Screen({ trial, phaseIndex, totalTrials, onSubmit, submitting }) {
  const [text, setText] = useState('');

  useEffect(() => {
    setText('');
  }, [trial?.trial_index]);

  if (!trial) {
    return null;
  }

  const remaining = 200 - text.length;

  return (
    <ScreenShell
      eyebrow={`${PHASE_LABELS.step_1} · ${phaseIndex + 1}/${totalTrials}`}
      title="Generative Captioning"
      description="Write a new caption from scratch that describes the acoustics of the space. Keep it under 200 characters."
      footer={
        <button className="primary-button" type="button" onClick={() => onSubmit(text)} disabled={!text.trim() || submitting}>
          Submit &amp; Next
        </button>
      }
    >
      <AudioBlock audioUrl={trial.audio_url} />
      <label className="text-area-shell">
        <span className="caption-label">Original caption</span>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value.slice(0, 200))}
          rows={6}
          maxLength={200}
          placeholder="Type your caption here..."
        />
      </label>
      <div className="countdown">{remaining} characters remaining</div>
    </ScreenShell>
  );
}

function Step2Screen({ trial, phaseIndex, totalTrials, onSubmit, submitting }) {
  const [text, setText] = useState(trial?.baseline_caption || '');

  useEffect(() => {
    setText(trial?.baseline_caption || '');
  }, [trial?.trial_index]);

  if (!trial) {
    return null;
  }

  return (
    <ScreenShell
      eyebrow={`${PHASE_LABELS.step_2} · ${phaseIndex + 1}/${totalTrials}`}
      title="Rephrasing / Editing"
      description="Edit the provided caption if you want to improve it, or leave it unchanged to accept it."
      footer={
        <button className="primary-button" type="button" onClick={() => onSubmit(text)} disabled={!text.trim() || submitting}>
          Submit &amp; Next
        </button>
      }
    >
      <AudioBlock audioUrl={trial.audio_url} baseline={trial.baseline_caption} showBaseline />
      <label className="text-area-shell" padding_top="5px">
        <span className="caption-label">Edit the caption</span>
        <textarea value={text} onChange={(event) => setText(event.target.value)} rows={6} />
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
  console.log(trial.selected_caption)
  console.log(trial.baseline_caption)
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
      <AudioBlock audioUrl={trial.audio_url} baseline={trial.baseline_caption} showBaseline />
      <section className="stack">
        <div className="field-group">
          <div className="field-heading">
            <h2>Grammar Correctness</h2>
            <p>How grammatical is the caption?</p>
          </div>
          <GrammarScale value={grammarRating} onChange={setGrammarRating} />
        </div>
        <div className="field-group">
          <div className="field-heading">
            <h2>Accuracy of the Description</h2>
            <p>How accurately does the caption describe the acoustics?</p>
          </div>
          <AccuracyScale value={accuracyRating} onChange={setAccuracyRating} />
        </div>
      </section>
    </ScreenShell>
  );
}

function TrainingStep1Screen({ trial, onSubmit }) {
  const [text, setText] = useState('');
  const remaining = 200 - text.length;
  const baseline = "The room sounds small and dry, with very little reverberation.";

  return (
    <ScreenShell
      eyebrow="Training · Step 1"
      title="Practice: Generative Captioning"
      description="This is a practice round to familiarize you with the task. Listen to the training audio below and practice writing a descriptive caption from scratch. Keep it under 200 characters."
      footer={
        <button className="primary-button" type="button" onClick={onSubmit} disabled={!text.trim()}>
          Continue to Step 2 Practice
        </button>
      }
    >
      <AudioBlock audioUrl={trial.audio_url} baseline={baseline} />
      
      {/* Examples Block: Changed to a div with a standard list */}
      <div className="caption-box caption-box-muted" style={{ marginBottom: '10px' }}>
        <span className="caption-label">Training: Examples of Captions</span>
        <ul style={{ margin: '8px 0 0 0', paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <li>Unique New York</li>
          <li>How now Brown Cow</li>
          <li>Something Something</li>
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

function TrainingStep2Screen({ trial, onSubmit }) {
  // Hardcoded baseline for the training example
  const baseline = "The room sounds small and dry, with very little reverberation.";
  const [text, setText] = useState(baseline);

  return (
    <ScreenShell
      eyebrow="Training · Step 2"
      title="Practice: Rephrasing / Editing"
      description="Now practice the editing step. Edit the provided baseline caption if you want to improve it, or leave it unchanged."
      footer={
        <button className="primary-button" type="button" onClick={onSubmit} disabled={!text.trim()}>
          Start Actual Survey
        </button>
      }
    >
      <div className="caption-box" style={{ marginBottom: '10px' }}>
        <span className="caption-label">Training: Editing the Caption</span>
        <ul style={{ margin: '8px 0 0 0', paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <li>In questions like this, you will be asked to listen to the audio presented and review the caption paired with that audio.</li>
          <li>You can edit the caption should find any Grammatical errors, clarity, or accuracy issues.</li>
          <li>It is a valid option to leave the caption unedited and then click the Continue button in the bottom right.</li>
        </ul>
      </div>
      <AudioBlock audioUrl={trial.audio_url} baseline={baseline} showBaseline />
      <label className="text-area-shell" style={{ paddingTop: '5px' }}>
        <span className="caption-label">Edit the caption</span>
        <textarea value={text} onChange={(event) => setText(event.target.value)} rows={6} />
      </label>
    </ScreenShell>
  );
}

export default function App() {
  const prolificContext = useMemo(() => parseQueryParams(), []);
  const completionUrl = useMemo(() => buildCompletionUrl(prolificContext), [prolificContext]);
  const [phase, setPhase] = useState('intro');
  const [stimuli, setStimuli] = useState(null);
  const [training, setTraining] = useState(null);
  const [demographics, setDemographics] = useState({ age_range: '', experience_in_audio: '' });
  const [trialIndex, setTrialIndex] = useState({ 
      training_step_1: 0,
      training_step_2: 0,
      step_1: 0, 
      step_2: 0, 
      step_3: 0
  });
  const [statusMessage, setStatusMessage] = useState('Loading survey...');
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
        setStimuli(data.stimuli);
        setTraining(data.training);
        setStatusMessage('Survey ready.');
      } catch (error) {
        setStatusMessage(error instanceof Error ? error.message : 'Failed to load stimuli.');
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
          batch_id: stimuli?.batch_id || '',
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
          // Redirect to training instead of step_1
          setPhase('training_step_1'); 
        }}
      />
    );
  }

  if (phase === 'blocked') {
    return <BlockedScreen />;
  }

  if (phase === 'training_step_1') {
    const trial = training?.training_step_1;
    console.log(trial)
    return (
      <TrainingStep1Screen 
        trial={trial}
        onSubmit={() => setPhase('training_step_2')} 
      />
    );
  }

  if (phase === 'training_step_2') {
    const trial = training?.training_step_2;
    return (
      <TrainingStep2Screen 
        trial={trial}
        onSubmit={() => setPhase('step_1')} 
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
    return <CompletionScreen completionUrl={completionUrl} />;
  }

  return <ScreenShell eyebrow="Loading" title="Preparing study" description={statusMessage} />;
}