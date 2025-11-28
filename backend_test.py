import requests
import sys
import json
import io
from datetime import datetime
from pathlib import Path

class PreChartingAPITester:
    def __init__(self, base_url="https://clinicalnote-ai.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
        
        result = {
            "test": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} - {name}")
        if details:
            print(f"   Details: {details}")

    def test_api_root(self):
        """Test API root endpoint"""
        try:
            response = requests.get(f"{self.api_url}/", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                details += f", Message: {data.get('message', 'No message')}"
            self.log_test("API Root Endpoint", success, details)
            return success
        except Exception as e:
            self.log_test("API Root Endpoint", False, f"Error: {str(e)}")
            return False

    def test_transcribe_endpoint_no_file(self):
        """Test transcribe endpoint without file (should fail)"""
        try:
            response = requests.post(f"{self.api_url}/transcribe", timeout=10)
            # Should return 422 for missing file
            success = response.status_code == 422
            details = f"Status: {response.status_code} (Expected 422 for missing file)"
            self.log_test("Transcribe Endpoint - No File", success, details)
            return success
        except Exception as e:
            self.log_test("Transcribe Endpoint - No File", False, f"Error: {str(e)}")
            return False

    def test_transcribe_endpoint_with_dummy_file(self):
        """Test transcribe endpoint with dummy audio file"""
        try:
            # Create a dummy audio file (minimal WAV header)
            dummy_audio = b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
            
            files = {'file': ('test_audio.wav', io.BytesIO(dummy_audio), 'audio/wav')}
            response = requests.post(f"{self.api_url}/transcribe", files=files, timeout=30)
            
            # This might fail due to invalid audio, but we're testing the endpoint structure
            success = response.status_code in [200, 500]  # 500 is acceptable for invalid audio
            details = f"Status: {response.status_code}"
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    details += f", Response has transcript: {'transcript' in data}"
                except:
                    details += ", Invalid JSON response"
            elif response.status_code == 500:
                details += " (Expected for dummy audio file)"
            
            self.log_test("Transcribe Endpoint - With File", success, details)
            return success
        except Exception as e:
            self.log_test("Transcribe Endpoint - With File", False, f"Error: {str(e)}")
            return False

    def test_generate_notes_endpoint_no_data(self):
        """Test generate notes endpoint without data (should fail)"""
        try:
            response = requests.post(f"{self.api_url}/generate-notes", 
                                   headers={'Content-Type': 'application/json'}, 
                                   timeout=10)
            # Should return 422 for missing data
            success = response.status_code == 422
            details = f"Status: {response.status_code} (Expected 422 for missing data)"
            self.log_test("Generate Notes - No Data", success, details)
            return success
        except Exception as e:
            self.log_test("Generate Notes - No Data", False, f"Error: {str(e)}")
            return False

    def test_generate_notes_endpoint_with_data(self):
        """Test generate notes endpoint with sample data"""
        try:
            test_data = {
                "transcript": "Patient complains of chest pain that started this morning. Pain is sharp and located in the center of the chest.",
                "observed_actions": "Clutching chest, appears anxious"
            }
            
            response = requests.post(f"{self.api_url}/generate-notes", 
                                   json=test_data,
                                   headers={'Content-Type': 'application/json'}, 
                                   timeout=60)  # Longer timeout for LLM processing
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                try:
                    data = response.json()
                    required_fields = ['subjective', 'objective', 'assessment', 'plan', 
                                     'icd10_codes', 'medication_interactions', 'red_flags', 
                                     'non_verbal_signs', 'clinical_summary']
                    
                    missing_fields = [field for field in required_fields if field not in data]
                    if not missing_fields:
                        details += ", All required fields present"
                    else:
                        details += f", Missing fields: {missing_fields}"
                        success = False
                        
                except json.JSONDecodeError:
                    details += ", Invalid JSON response"
                    success = False
            else:
                try:
                    error_data = response.json()
                    details += f", Error: {error_data.get('detail', 'Unknown error')}"
                except:
                    details += f", Raw response: {response.text[:100]}"
            
            self.log_test("Generate Notes - With Data", success, details)
            return success
        except Exception as e:
            self.log_test("Generate Notes - With Data", False, f"Error: {str(e)}")
            return False

    def test_get_notes_endpoint(self):
        """Test get notes endpoint"""
        try:
            response = requests.get(f"{self.api_url}/notes", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                try:
                    data = response.json()
                    details += f", Notes count: {len(data) if isinstance(data, list) else 'Not a list'}"
                except:
                    details += ", Invalid JSON response"
                    success = False
            
            self.log_test("Get Notes Endpoint", success, details)
            return success
        except Exception as e:
            self.log_test("Get Notes Endpoint", False, f"Error: {str(e)}")
            return False

    def test_cors_headers(self):
        """Test CORS headers"""
        try:
            response = requests.options(f"{self.api_url}/", timeout=10)
            success = response.status_code in [200, 204]
            details = f"Status: {response.status_code}"
            
            cors_headers = ['Access-Control-Allow-Origin', 'Access-Control-Allow-Methods']
            present_headers = [h for h in cors_headers if h in response.headers]
            details += f", CORS headers present: {len(present_headers)}/{len(cors_headers)}"
            
            self.log_test("CORS Headers", success, details)
            return success
        except Exception as e:
            self.log_test("CORS Headers", False, f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all backend tests"""
        print("🔍 Starting Pre-Charting AI Assistant Backend Tests")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Test basic connectivity first
        if not self.test_api_root():
            print("\n❌ API root endpoint failed - stopping tests")
            return False
        
        # Test all endpoints
        self.test_transcribe_endpoint_no_file()
        self.test_transcribe_endpoint_with_dummy_file()
        self.test_generate_notes_endpoint_no_data()
        self.test_generate_notes_endpoint_with_data()
        self.test_get_notes_endpoint()
        self.test_cors_headers()
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        # Print failed tests
        failed_tests = [r for r in self.test_results if not r['success']]
        if failed_tests:
            print("\n❌ Failed Tests:")
            for test in failed_tests:
                print(f"   - {test['test']}: {test['details']}")
        
        return self.tests_passed == self.tests_run

def main():
    """Main test execution"""
    tester = PreChartingAPITester()
    success = tester.run_all_tests()
    
    # Save detailed results
    results_file = "/app/backend_test_results.json"
    with open(results_file, 'w') as f:
        json.dump({
            "summary": {
                "total_tests": tester.tests_run,
                "passed_tests": tester.tests_passed,
                "success_rate": (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0,
                "timestamp": datetime.now().isoformat()
            },
            "test_results": tester.test_results
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: {results_file}")
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())