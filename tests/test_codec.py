import unittest
from PIL import Image
from cat_chat import encode, decode

class CarrierTests(unittest.TestCase):
    def test_unicode_and_pixel_preservation(self):
        source = Image.new('RGB', (160, 160), (50, 120, 240))
        message = 'Hello cat! 🐈 árvíz'
        png = encode(source, message, 'a shared secret')
        text, carrier = decode(png, 'a shared secret')
        self.assertEqual(text, message)
        self.assertEqual(source.size, carrier.size)
        self.assertTrue(all(abs(a-b) <= 1 for a,b in zip(source.tobytes(), carrier.tobytes())))

    def test_wrong_secret_rejected(self):
        png = encode(Image.new('RGB', (160, 160)), 'secret message', 'correct')
        with self.assertRaises(ValueError): decode(png, 'wrong')

    def test_capacity_rejected(self):
        with self.assertRaises(ValueError): encode(Image.new('RGB', (1, 1)), 'too large', 'secret')

    def test_plain_image_rejected(self):
        import io
        output = io.BytesIO()
        Image.new('RGB', (100, 100)).save(output, format='PNG')
        with self.assertRaises(ValueError): decode(output.getvalue(), 'secret')

if __name__ == '__main__': unittest.main()
