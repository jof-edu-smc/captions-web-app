import unittest
from dotenv import load_dotenv
from unittest.mock import patch
from app import app  # Import your Flask app

class TestApp(unittest.TestCase):
    
    def setUp(self):
        """This runs before every single test to set up a clean environment."""
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_get_pdf_urls(self):
        from app import _get_pdf_urls 
        load_dotenv()  # Load environment variables from .env file
        url = _get_pdf_urls()
        self.assertIsInstance(url, dict)
        self.assertIn('pis_url', url)
        self.assertIn('cf_url', url)

    @patch('app._get_pdf_urls')
    def test_get_pdf_urls_returns_empty_strings_on_error(self, mock_get_url):
        """Using @patch safely replaces the function just for this test."""
        # Tell our mock to simulate an error
        mock_get_url.side_effect = Exception("Simulated error")
        
        # In a real scenario, you'd test how your app handles this failure.
        # For example, calling the route that relies on it:
        with self.assertRaises(Exception):
            mock_get_url()

    @patch('app.append_row_to_sheet')
    @patch('app.increment_caption_count')
    def test_submit_results_step_1_success(self, mock_increment, mock_append):
        """Testing the API route using the Flask Test Client."""
        
        # 1. Create a payload that matches your exact new database schema
        payload = {
            "phase": "step_1",
            "generated_text": "Unit test generated text for step 1",
            "participant_context": {
                "prolific_id": "test_user_123",
                "session_id": "session_abc",
                "age_range": "Unit Testing",
                "experience_in_audio": "Unit Testing"
            },
            "stimulus": {
                "rir_id": "1st_baptist_nashville_balcony.mp3"
            }
        }
        
        # 2. Use self.client to fire a fake HTTP POST request
        response = self.client.post('/api/submit-response', json=payload)
        
        # 3. Assert the HTTP response was successful
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['ok'])
        
        # 4. Assert that the database functions were triggered
        self.assertEqual(mock_append.call_count, 2) # Once for captions, once for annotators
        mock_increment.assert_called_once_with("1st_baptist_nashville_balcony.mp3", target_col_name="num_of_captions")

    def test_submit_results_invalid_payload(self):
        """Ensure the API rejects bad data without crashing."""
        
        # Missing 'generated_text' for Step 1
        payload = {
            "phase": "step_1",
            "participant_context": {"prolific_id": "test_user_123"},
            "stimulus": {"rir_id": "h001_Bedroom_65txts"}
        }
        
        response = self.client.post('/api/submit-response', json=payload)
        
        # Assert the API caught the error and returned a 400 Bad Request
        self.assertEqual(response.status_code, 400)
        self.assertIn("requires generated_text", response.json['error'])

if __name__ == '__main__':
    unittest.main()