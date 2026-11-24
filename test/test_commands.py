import unittest
from presenter import decide

def result(text, conf=.95):
    return {'text':text,'result':[{'conf':conf} for _ in text.split()]}

class Tests(unittest.TestCase):
    def test_commands(self):
        for phrase, action in [('slide next','next'),('slide back','back'),('slide lanjut','next'),('slide kembali','back')]:
            self.assertEqual(decide(result(phrase),.85,0,2,1),action)
    def test_reject(self):
        for phrase in ['next','this slide next','slide next please','[unk] slide next','']:
            self.assertIsNone(decide(result(phrase),.85,0,2,1))
    def test_confidence(self):
        self.assertIsNone(decide(result('slide next',.7),.85,0,2,1))
    def test_cooldown(self):
        self.assertIsNone(decide(result('slide next'),.85,1.5,2,1))
    def test_missing_words(self):
        self.assertIsNone(decide({'text':'slide next'},.85,0,2,1))
