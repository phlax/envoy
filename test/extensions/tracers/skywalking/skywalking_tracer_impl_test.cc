#include "extensions/tracers/skywalking/skywalking_tracer_impl.h"

#include "test/extensions/tracers/skywalking/skywalking_test_helper.h"
#include "test/mocks/common.h"
#include "test/mocks/server/tracer_factory_context.h"
#include "test/mocks/tracing/mocks.h"
#include "test/test_common/utility.h"

#include "gmock/gmock.h"
#include "gtest/gtest.h"

using namespace testing;

namespace Envoy {
namespace Extensions {
namespace Tracers {
namespace SkyWalking {

class SkyWalkingDriverTest : public testing::Test {
public:
  void setupSkyWalkingDriver(const std::string& yaml_string) {
    auto mock_client_factory = std::make_unique<NiceMock<Grpc::MockAsyncClientFactory>>();
    auto mock_client = std::make_unique<NiceMock<Grpc::MockAsyncClient>>();
    mock_stream_ptr_ = std::make_unique<NiceMock<Grpc::MockAsyncStream>>();

    EXPECT_CALL(*mock_client, startRaw(_, _, _, _)).WillOnce(Return(mock_stream_ptr_.get()));
    EXPECT_CALL(*mock_client_factory, create()).WillOnce(Return(ByMove(std::move(mock_client))));

    auto& factory_context = context_.server_factory_context_;

    EXPECT_CALL(factory_context.cluster_manager_.async_client_manager_,
                factoryForGrpcService(_, _, _))
        .WillOnce(Return(ByMove(std::move(mock_client_factory))));

    ON_CALL(factory_context.local_info_, clusterName()).WillByDefault(ReturnRef(test_string));
    ON_CALL(factory_context.local_info_, nodeName()).WillByDefault(ReturnRef(test_string));

    TestUtility::loadFromYaml(yaml_string, config_);
    driver_ = std::make_unique<Driver>(config_, context_);
  }

protected:
  NiceMock<Envoy::Server::Configuration::MockTracerFactoryContext> context_;
  NiceMock<Envoy::Tracing::MockConfig> mock_tracing_config_;
  Event::SimulatedTimeSystem time_system_;

  std::unique_ptr<NiceMock<Grpc::MockAsyncStream>> mock_stream_ptr_{nullptr};

  envoy::config::trace::v3::SkyWalkingConfig config_;
  std::string test_string = "ABCDEFGHIJKLMN";

  DriverPtr driver_;
};

static const std::string SKYWALKING_CONFIG_WITH_CLIENT_CONFIG = R"EOF(
  grpc_service:
    envoy_grpc:
      cluster_name: fake_cluster
  client_config:
    authentication: "FAKE_FAKE_FAKE_FAKE_FAKE_FAKE"
    service_name: "FAKE_FAKE_FAKE"
    instance_name: "FAKE_FAKE_FAKE"
    pass_endpoint: true
    max_cache_size: 2333
)EOF";

static const std::string SKYWALKING_CONFIG_NO_CLIENT_CONFIG = R"EOF(
  grpc_service:
    envoy_grpc:
      cluster_name: fake_cluster
)EOF";

TEST_F(SkyWalkingDriverTest, SkyWalkingDriverStartSpanTestWithClientConfig) {
  setupSkyWalkingDriver(SKYWALKING_CONFIG_WITH_CLIENT_CONFIG);

  std::string trace_id = SkyWalkingTestHelper::generateId(context_.server_factory_context_.api_.random_);
  std::string segment_id =
      SkyWalkingTestHelper::generateId(context_.server_factory_context_.api_.random_);

  // Create new span segment with previous span context.
  std::string previous_header_value =
      fmt::format("{}-{}-{}-{}-{}-{}-{}-{}", 0, SkyWalkingTestHelper::base64Encode(trace_id),
                  SkyWalkingTestHelper::base64Encode(segment_id), 233333,
                  SkyWalkingTestHelper::base64Encode("SERVICE"),
                  SkyWalkingTestHelper::base64Encode("INSTATNCE"),
                  SkyWalkingTestHelper::base64Encode("ENDPOINT"),
                  SkyWalkingTestHelper::base64Encode("ADDRESS"));

  Http::TestRequestHeaderMapImpl request_headers{{"sw8", previous_header_value},
                                                 {":path", "/path"},
                                                 {":method", "GET"},
                                                 {":authority", "test.com"}};

  ON_CALL(mock_tracing_config_, operationName())
      .WillByDefault(Return(Tracing::OperationName::Ingress));

  Tracing::Decision decision;
  decision.traced = true;

  Tracing::SpanPtr org_span = driver_->startSpan(mock_tracing_config_, request_headers, "",
                                                 time_system_.systemTime(), decision);
  EXPECT_NE(nullptr, org_span.get());

  Span* span = dynamic_cast<Span*>(org_span.get());
  ASSERT(span);

  EXPECT_NE(nullptr, span->segmentContext()->previousSpanContext());

  EXPECT_EQ("FAKE_FAKE_FAKE", span->segmentContext()->service());
  EXPECT_EQ("FAKE_FAKE_FAKE", span->segmentContext()->serviceInstance());

  // If pass_endpoint is set to true, Envoy will use the downstream endpoint directly.
  EXPECT_EQ(span->segmentContext()->endpoint(),
            span->segmentContext()->previousSpanContext()->endpoint_);

  // Tracing decision will be overwrite by sampling flag in propagation headers.
  EXPECT_EQ(0, span->segmentContext()->sampled());

  // Since the sampling flag is false, no segment data is reported.
  span->finishSpan();

  auto& factory_context = context_.server_factory_context_;
  EXPECT_EQ(0U, factory_context.scope_.counter("tracing.skywalking.segments_sent").value());

  // Create new span segment with no previous span context.
  Http::TestRequestHeaderMapImpl new_request_headers{
      {":path", "/path"}, {":method", "GET"}, {":authority", "test.com"}};

  Tracing::SpanPtr org_new_span = driver_->startSpan(mock_tracing_config_, new_request_headers, "",
                                                     time_system_.systemTime(), decision);

  Span* new_span = dynamic_cast<Span*>(org_new_span.get());
  ASSERT(new_span);

  EXPECT_EQ(nullptr, new_span->segmentContext()->previousSpanContext());
  // Although pass_endpoint is set to true, 'METHOD' and 'PATH' will be used as endpoint when
  // previous span context is null.
  EXPECT_EQ("/GET/path", new_span->segmentContext()->endpoint());

  EXPECT_EQ(true, new_span->segmentContext()->sampled());

  EXPECT_CALL(*mock_stream_ptr_, sendMessageRaw_(_, _));
  new_span->finishSpan();
  EXPECT_EQ(1U, factory_context.scope_.counter("tracing.skywalking.segments_sent").value());

  // Create new span segment with error propagation header.
  Http::TestRequestHeaderMapImpl error_request_headers{{":path", "/path"},
                                                       {":method", "GET"},
                                                       {":authority", "test.com"},
                                                       {"sw8", "xxxxxx-error-propagation-header"}};
  Tracing::SpanPtr org_null_span = driver_->startSpan(mock_tracing_config_, error_request_headers,
                                                      "", time_system_.systemTime(), decision);

  EXPECT_EQ(nullptr, dynamic_cast<Span*>(org_null_span.get()));

  auto& null_span = *org_null_span;
  EXPECT_EQ(typeid(null_span).name(), typeid(Tracing::NullSpan).name());
}

TEST_F(SkyWalkingDriverTest, SkyWalkingDriverStartSpanTestNoClientConfig) {
  setupSkyWalkingDriver(SKYWALKING_CONFIG_NO_CLIENT_CONFIG);

  Http::TestRequestHeaderMapImpl request_headers{
      {":path", "/path"}, {":method", "GET"}, {":authority", "test.com"}};

  Tracing::SpanPtr org_span = driver_->startSpan(mock_tracing_config_, request_headers, "",
                                                 time_system_.systemTime(), Tracing::Decision());
  EXPECT_NE(nullptr, org_span.get());

  Span* span = dynamic_cast<Span*>(org_span.get());
  ASSERT(span);

  EXPECT_EQ(test_string, span->segmentContext()->service());
  EXPECT_EQ(test_string, span->segmentContext()->serviceInstance());
  EXPECT_EQ("/GET/path", span->segmentContext()->endpoint());
}

} // namespace SkyWalking
} // namespace Tracers
} // namespace Extensions
} // namespace Envoy
