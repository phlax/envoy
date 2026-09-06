#include "source/common/tls/ocsp/ocsp.h"

#include "test/common/tls/ssl_test_utility.h"
#include "test/test_common/environment.h"
#include "test/test_common/simulated_time_system.h"
#include "test/test_common/utility.h"

#include "gtest/gtest.h"

// Verifies that the OCSP responses //tools/testcerts:gen produces are
// well-formed and carry the status and validity window the spec asks for. This
// replaces the human-readable `*_ocsp_resp_details.txt` dumps that the old
// the old offline fixture generation scripts wrote next to each response.
namespace Envoy {
namespace {

using Extensions::TransportSockets::Tls::Ocsp::OcspResponseStatus;
using Extensions::TransportSockets::Tls::Ocsp::OcspResponseWrapperImpl;

class GeneratedOcspResponseTest : public testing::Test {
public:
  std::vector<uint8_t> readResponse(const std::string& filename) {
    const auto str = TestEnvironment::readFileToStringForTest(TestEnvironment::substitute(
        "{{ test_rundir }}/test/common/tls/ocsp/test_data/" + filename));
    return {str.begin(), str.end()};
  }

  bssl::UniquePtr<X509> readCert(const std::string& filename) {
    return Extensions::TransportSockets::Tls::readCertFromFile(TestEnvironment::substitute(
        "{{ test_rundir }}/test/common/tls/ocsp/test_data/" + filename));
  }

protected:
  Event::SimulatedTimeSystem time_system_;
};

// A response with a nextUpdate in the future parses, matches the certificate it
// was generated for and is not yet expired.
TEST_F(GeneratedOcspResponseTest, GoodResponseIsValid) {
  auto response = OcspResponseWrapperImpl::create(readResponse("good_ocsp_resp.der"), time_system_);
  ASSERT_TRUE(response.ok());

  EXPECT_EQ(OcspResponseStatus::Successful, (*response)->getResponseStatus());
  EXPECT_TRUE((*response)->matchesCertificate(*readCert("good_cert.pem")));
  EXPECT_FALSE((*response)->matchesCertificate(*readCert("revoked_cert.pem")));

  // The generator stamps `next_update_days = 730` onto this fixture, so it must
  // stay valid for the best part of two years after every regeneration.
  EXPECT_FALSE((*response)->isExpired());
  EXPECT_GT((*response)->secondsUntilExpiration(), 0);
}

// Responses generated without a nextUpdate are always treated as expired.
TEST_F(GeneratedOcspResponseTest, ResponseWithoutNextUpdateIsExpired) {
  auto response =
      OcspResponseWrapperImpl::create(readResponse("revoked_ocsp_resp.der"), time_system_);
  ASSERT_TRUE(response.ok());

  EXPECT_EQ(OcspResponseStatus::Successful, (*response)->getResponseStatus());
  EXPECT_TRUE((*response)->matchesCertificate(*readCert("revoked_cert.pem")));
  EXPECT_TRUE((*response)->isExpired());
  EXPECT_EQ(0, (*response)->secondsUntilExpiration());
}

// The multi-certificate fixture really does carry two SingleResponse entries,
// which Envoy rejects.
TEST_F(GeneratedOcspResponseTest, MultipleCertificateResponseIsRejected) {
  EXPECT_EQ(
      OcspResponseWrapperImpl::create(readResponse("multiple_cert_ocsp_resp.der"), time_system_)
          .status()
          .message(),
      "OCSP Response must be for one certificate only");
}

} // namespace
} // namespace Envoy
