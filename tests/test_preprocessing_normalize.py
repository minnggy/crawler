import unittest

try:
    import pandas as pd
    from preprocessing_normalize import preprocess_dataframe
except ImportError:  # local crawler's stdlib-only runtime may not include pandas
    pd = None


@unittest.skipIf(pd is None, "requires pandas")
class NormalizeTests(unittest.TestCase):
    def test_salary_geo_taxonomy_and_text(self):
        frame = pd.DataFrame([{
            "min_salary": "$25", "max_salary": "30", "pay_period": "HOURLY", "currency": "usd",
            "location": "New York, NY, United States", "formatted_work_type": "Full-time",
            "formatted_experience_level": "Mid-Senior level", "title": "Senior Data Analyst",
            "description": "Email a@b.com", "job_skills": "Python, SQL",
        }])
        result = preprocess_dataframe(frame, redact_pii=True)
        self.assertEqual(result.loc[0, "salary_annualized"], 57200)
        self.assertEqual(result.loc[0, "country"], "United States")
        self.assertEqual(result.loc[0, "work_type_standard"], "Full-time")
        self.assertEqual(result.loc[0, "job_family"], "Data/Analytics")
        self.assertIn("[EMAIL]", result.loc[0, "description_clean"])
        self.assertTrue(result.loc[0, "has_skills"])

    def test_invalid_salary_is_flagged(self):
        frame = pd.DataFrame([{"min_salary": 100, "max_salary": 50, "pay_period": "YEARLY"}])
        result = preprocess_dataframe(frame)
        self.assertFalse(result.loc[0, "salary_order_valid"])
        self.assertFalse(result.loc[0, "salary_valid_for_analysis"])


if __name__ == "__main__":
    unittest.main()
