"""Re-check method C — natural language inference (NLI).

An NLI model is a small classifier, not a chatbot. Given a PREMISE (the policy section)
and a HYPOTHESIS (one sentence of TrustGuard's suggested answer) it outputs three
probabilities: entailment (the premise guarantees the sentence), contradiction, neutral
(the premise neither guarantees nor rules it out). It cannot write text, so it cannot
"talk itself into" agreeing, and it was trained on different data from the LLM that
wrote the correction. That independence is the point of using it here.

Weakness to state honestly: NLI models are weak with exact numbers. That is why
methods A and B (plain code) check numbers, and NLI checks meaning.

Loaded lazily and optional: if the model can't be downloaded or sentence-transformers
isn't installed, `available` is False and the UI says method C was skipped.
"""
import threading

import numpy as np

import config


class NLIChecker:
    def __init__(self, model_name: str = config.NLI_MODEL, enabled: bool = config.ENABLE_NLI):
        self.model_name, self.enabled = model_name, enabled
        self._model, self._labels, self.error = None, None, ""
        self._lock = threading.Lock()
        self._tried = False

    def _load(self) -> None:
        with self._lock:
            if self._tried:
                return
            self._tried = True
            if not self.enabled:
                self.error = "Method C is switched off (ENABLE_NLI=false)."
                return
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
                id2label = self._model.model.config.id2label
                self._labels = [id2label[i].lower() for i in range(len(id2label))]
            except Exception as e:  # no internet on first run, missing torch, unknown model...
                self._model = None
                self.error = f"Entailment model unavailable ({type(e).__name__}); method C was skipped."

    @property
    def available(self) -> bool:
        self._load()
        return self._model is not None

    def check(self, premise: str, hypothesis: str) -> dict:
        """Returns {"label": entailment|neutral|contradiction, "entailment": p, ...}."""
        if not self.available:
            return {"label": "unavailable", "note": self.error}
        scores = np.asarray(self._model.predict([(premise, hypothesis)], convert_to_numpy=True))[0]
        if not (np.all(scores >= 0) and abs(float(scores.sum()) - 1) < 1e-3):
            scores = np.exp(scores - scores.max())
            scores = scores / scores.sum()  # logits -> probabilities
        probs = {label: float(p) for label, p in zip(self._labels, scores)}
        ent, con = probs.get("entailment", 0.0), probs.get("contradiction", 0.0)
        if ent >= config.NLI_ENTAIL_THRESHOLD and ent >= con:
            label = "entailment"
        elif con >= config.NLI_ENTAIL_THRESHOLD:
            label = "contradiction"
        else:
            label = "neutral"
        return {"label": label, **{k: round(v, 3) for k, v in probs.items()}}
