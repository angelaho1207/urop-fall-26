"""Prompts for naming (N4), the detection and fuzzing quizzes (N5, N6) and the name-match judge (N10).

Texts are copied from EleutherAI delphi at commit 4fea06e6e8b68eeaf302474325fca13df95c5d6f:
  delphi/explainers/default/prompts.py   (SYSTEM, EXAMPLE_1-3_ACTIVATIONS, EXAMPLE_1-3_EXPLANATION)
  delphi/scorers/classifier/prompts/detection_prompt.py
  delphi/scorers/classifier/prompts/fuzz_prompt.py
Changes, each recorded in design.md: answers come back as structured JSON (N4a, N5, N6), so the format instructions
and the worked answers are rewritten for JSON; newlines show as ⏎ (N4b); the GPT-2 byte artifacts in the quiz worked
examples are decoded (N5); the worked naming examples use the `("token" : n)` form of delphi's actual examples
(N13e). The judge prompt is ours (N10).
"""
import codecs
import json

NEWLINE = "⏎"  # N4b


# --- GPT-2 byte artifacts (N5) ---------------------------------------------------------------------------------
def _gpt2_byte_decoder():
    """Inverse of GPT-2's bytes_to_unicode table: each printable stand-in character back to its byte."""
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {chr(c): b for b, c in zip(bs, cs)}


_BYTE_OF = _gpt2_byte_decoder()


def decode_gpt2_artifacts(text):
    """Turn delphi's raw GPT-2 token text (e.g. 'Ċ', 'âĢĻ') into readable text; drop <|endoftext|>.

    Characters outside GPT-2's stand-in table (e.g. ordinary spaces, already decoded) are kept as their UTF-8 bytes.
    """
    # 'Ċ' is GPT-2's stand-in for a newline inside the example text: show it as ⏎ (N4b). The "\n" characters are the
    # prompt's own line breaks; they are not in GPT-2's stand-in table, so the loop below keeps them as they are.
    text = text.replace("<|endoftext|>", "").replace("Ċ", NEWLINE)
    data = bytearray()
    for ch in text:
        if ch in _BYTE_OF and ch not in " ":
            data.append(_BYTE_OF[ch])
        else:
            data.extend(ch.encode("utf-8"))
    return data.decode("utf-8", errors="ignore")  # "ignore" drops split-character fragments such as a lone 'ľ'


# --- JSON answer formats ------------------------------------------------------------------------------------------
EXPLANATION_SCHEMA = {"type": "object", "properties": {"explanation": {"type": "string"}},
                      "required": ["explanation"], "additionalProperties": False}
ANSWERS_SCHEMA = {"type": "object",
                  "properties": {"answers": {"type": "array", "items": {"type": "integer", "enum": [0, 1]}}},
                  "required": ["answers"], "additionalProperties": False}
JUDGE_SCHEMA = {"type": "object", "properties": {"same": {"type": "boolean"}},
                "required": ["same"], "additionalProperties": False}

# --- Naming (N4) --------------------------------------------------------------------------------------------------
# delphi SYSTEM with cot=False ({prompt} = ""); the last guideline is rewritten for the JSON answer (N4a)
NAMING_SYSTEM = """You are a meticulous AI researcher conducting an important investigation into patterns found in language. Your task is to analyze text and provide an explanation that thoroughly encapsulates possible patterns found in it.
Guidelines:

You will be given a list of text examples on which special words are selected and between delimiters like <<this>>. If a sequence of consecutive tokens all are important, the entire sequence of tokens will be contained between delimiters <<just like this>>. How important each token is for the behavior is listed after each example in parentheses.

- Try to produce a concise final description. Simply describe the text latents that are common in the examples, and what patterns you found.
- If the examples are uninformative, you don't need to mention them. Don't focus on giving examples of important tokens, but try to summarize the patterns found in the examples.
- Do not mention the marker tokens (<< >>) in your explanation.
- Do not make lists of possible explanations. Keep your explanations short and concise.
- Give your final explanation in the "explanation" field of your JSON answer.

"""

# delphi EXAMPLE_n_ACTIVATIONS (activation lines in the ("token" : n) form of delphi's actual examples, N13e)
_NAMING_EXAMPLES = [
    ("""
Example 1:  and he was <<over the moon>> to find
Activations: ("over" : 5), (" the" : 6), (" moon" : 9),
Example 2:  we'll be laughing <<till the cows come home>>! Pro
Activations: ("till" : 5), (" the" : 5), (" cows" : 8), (" come" : 8), (" home" : 8),
Example 3:  thought Scotland was boring, but really there's more <<than meets the eye>>! I'd
Activations: ("than" : 5), (" meets" : 7), (" the" : 6), (" eye" : 8),
""", "Common idioms in text conveying positive sentiment."),
    ("""
Example 1:  a river is wide but the ocean is wid<<er>>. The ocean
Activations: ("er" : 8),
Example 2:  every year you get tall<<er>>," she
Activations: ("er" : 2),
Example 3:  the hole was small<<er>> but deep<<er>> than the
Activations: ("er" : 9), ("er" : 9),
""", 'The token "er" at the end of a comparative adjective describing size.'),
    ("""
Example 1:  something happening inside my <<house>>", he
Activations: ("house" : 7),
Example 2:  presumably was always contained in <<a box>>", according
Activations: ("a" : 5), ("box" : 9),
Example 3:  people were coming into the <<smoking area>>".⏎⏎However he
Activations: ("smoking" : 2), ("area" : 4),
Example 4:  Patrick: "why are you getting in the << way?>>" Later,
Activations: ("way" : 4), ("?" : 2),
""", "Nouns representing a distinct objects that contains something, sometimes preciding a quotation mark."),
]


def naming_messages(examples_text):
    """System prompt, the 3 worked examples as user/assistant turns, then the concept's 40 examples (N4)."""
    messages = []
    for user, explanation in _NAMING_EXAMPLES:
        messages.append({"role": "user", "content": user})
        messages.append({"role": "assistant", "content": json.dumps({"explanation": explanation})})
    messages.append({"role": "user", "content": f"\n{examples_text}\n"})
    return NAMING_SYSTEM, messages


# --- Quizzes (N5, N6) ---------------------------------------------------------------------------------------------
_FORMAT_LINE = ("You must return your response in a valid Python list. "
                "Do not return anything else besides a Python list.")
_JSON_LINE = ('Return your answers in the "answers" field of your JSON answer: one value, 1 or 0, per example, '
              "in the order of the examples.")  # N5, N6: replaces _FORMAT_LINE

DETECTION_SYSTEM = """You are an intelligent and meticulous linguistics researcher.

You will be given a certain latent of text, such as "male pronouns" or "text with negative sentiment".

You will then be given several text examples. Your task is to determine which examples possess the latent.

For each example in turn, return 1 if the sentence is correctly labeled or 0 if the tokens are mislabeled. You must return your response in a valid Python list. Do not return anything else besides a Python list.
""".replace(_FORMAT_LINE, _JSON_LINE)

FUZZ_SYSTEM = """You are an intelligent and meticulous linguistics researcher.

You will be given a certain latent of text, such as "male pronouns" or "text with negative sentiment". You will be given a few examples of text that contain this latent. Portions of the sentence which strongly represent this latent are between tokens << and >>.

Some examples might be mislabeled. Your task is to determine if every single token within << and >> is correctly labeled. Consider that all provided examples could be correct, none of the examples could be correct, or a mix. An example is only correct if every marked token is representative of the latent

For each example in turn, return 1 if the sentence is correctly labeled or 0 if the tokens are mislabeled. You must return your response in a valid Python list. Do not return anything else besides a Python list.
""".replace(_FORMAT_LINE, _JSON_LINE)

assert _JSON_LINE in DETECTION_SYSTEM and _JSON_LINE in FUZZ_SYSTEM  # the replacement must have happened

_DETECTION_EXAMPLES = [
    ("""Latent explanation: Words related to American football positions, specifically the tight end position.

Test examples:

Example 0:<|endoftext|>Getty ImagesĊĊPatriots tight end Rob Gronkowski had his bossâĢĻ
Example 1: names of months used in The Lord of the Rings:ĊĊâĢľâĢ¦the
Example 2: Media Day 2015ĊĊLSU defensive end Isaiah Washington (94) speaks to the
Example 3: shown, is generally not eligible for ads. For example, videos about recent tragedies,
Example 4: line, with the left side âĢĶ namely tackle Byron Bell at tackle and guard Amini
""", [1, 0, 0, 0, 1]),
    ("""Latent explanation: The word "guys" in the phrase "you guys".

Test examples:

Example 0: enact an individual health insurance mandate?âĢĿ, Pelosi's response was to dismiss both
Example 1: birth control access<|endoftext|> but I assure you women in Kentucky aren't laughing as they struggle
Example 2: du Soleil Fall Protection Program with construction requirements that do not apply to theater settings because
Example 3:Ċ<|endoftext|> distasteful. Amidst the slime lurk bits of Schadenfre
Example 4: the<|endoftext|>ľI want to remind you all that 10 days ago (director Massimil
""", [0, 0, 0, 0, 0]),
    ("""Latent explanation: "of" before words that start with a capital letter.

Test examples:

Example 0: climate, TomblinâĢĻs Chief of Staff Charlie Lorensen said.Ċ
Example 1: no wonderworking relics, no true Body and Blood of Christ, no true Baptism
Example 2:ĊĊDeborah Sathe, Head of Talent Development and Production at Film London,
Example 3:ĊĊIt has been devised by Director of Public Prosecutions (DPP)
Example 4: and fair investigation not even include the Director of Athletics? Â· Finally, we believe the
""", [1, 1, 1, 1, 1]),
]

_FUZZ_EXAMPLES = [
    ("""Latent explanation: Words related to American football positions, specifically the tight end position.

Test examples:

Example 0:<|endoftext|>Getty ImagesĊĊPatriots<< tight end>> Rob Gronkowski had his bossâĢĻ
Example 1: posted<|endoftext|>You should know this<< about>> offensive line coaches: they are large, demanding<< men>>
Example 2: Media Day 2015ĊĊLSU<< defensive>> end Isaiah Washington (94) speaks<< to the>>
Example 3:<< running backs>>," he said. .. Defensive<< end>> Carroll Phillips is improving and his injury is
Example 4:<< line>>, with the left side âĢĶ namely<< tackle>> Byron Bell at<< tackle>> and<< guard>> Amini
""", [1, 0, 0, 1, 1]),
    ("""Latent explanation: The word "guys" in the phrase "you guys".

Test examples:

Example 0: if you are<< comfortable>> with it. You<< guys>> support me in many other ways already and
Example 1: birth control access<|endoftext|> but I assure you<< women>> in Kentucky aren't laughing as they struggle
Example 2:âĢĻs gig! I hope you guys<< LOVE>> her, and<< please>> be nice,
Example 3:American, told<< Hannity>> that âĢľyou<< guys>> are playing the race card.âĢĿ
Example 4:<< the>><|endoftext|>ľI want to<< remind>> you all that 10 days ago (director Massimil
""", [0, 0, 0, 0, 0]),
    ("""Latent explanation: "of" before words that start with a capital letter.

Test examples:

Example 0: climate, TomblinâĢĻs Chief<< of>> Staff Charlie Lorensen said.Ċ
Example 1: no wonderworking relics, no true Body and Blood<< of>> Christ, no true Baptism
Example 2:ĊĊDeborah Sathe, Head<< of>> Talent Development and Production at Film London,
Example 3:ĊĊIt has been devised by Director<< of>> Public Prosecutions (DPP)
Example 4: and fair investigation not even include the Director<< of>> Athletics? Â· Finally, we believe the
""", [1, 1, 1, 1, 1]),
]

QUIZ_GENERATION = """Latent explanation: {explanation}

Text examples:

{examples}
"""


def quiz_messages(kind, explanation, examples_text):
    """System prompt, the 3 worked examples (artifacts decoded), then the 5 test examples (N5, N6)."""
    system, worked = {"detection": (DETECTION_SYSTEM, _DETECTION_EXAMPLES), "fuzz": (FUZZ_SYSTEM, _FUZZ_EXAMPLES)}[kind]
    messages = []
    for user, answers in worked:
        messages.append({"role": "user", "content": decode_gpt2_artifacts(user)})
        messages.append({"role": "assistant", "content": json.dumps({"answers": answers})})
    messages.append({"role": "user", "content": QUIZ_GENERATION.format(explanation=explanation, examples=examples_text)})
    return system, messages


# --- Name-match judge (N10, our own prompt) -----------------------------------------------------------------------
JUDGE_SYSTEM = """You compare two descriptions of the pattern of text that a single feature of a language model responds to. Each description was written from a different sample of text where the feature is active.

Decide whether the two descriptions describe the same pattern: the same kind of text and, where they say so, the same words or tokens. Differences only in wording, level of detail or emphasis count as the same pattern. A different topic, a different kind of token, or a different context counts as a different pattern.

Answer in the "same" field of your JSON answer: true if they describe the same pattern, false otherwise."""


def judge_messages(name_a, name_b):
    return JUDGE_SYSTEM, [{"role": "user", "content": f"Description A: {name_a}\n\nDescription B: {name_b}"}]


# --- Window text (N13g) -------------------------------------------------------------------------------------------
def token_pieces(byte_tokens):
    """Readable text per token from the tokenizer's byte-level token strings (convert_ids_to_tokens). Bytes are
    decoded incrementally, so a character split across tokens appears whole on the token that completes it (the
    earlier tokens get ""); bytes cut off at the window's edges are dropped. Newlines show as ⏎ (N4b)."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
    return [decoder.decode(bytes(_BYTE_OF[ch] for ch in t)).replace("\n", NEWLINE) for t in byte_tokens]
