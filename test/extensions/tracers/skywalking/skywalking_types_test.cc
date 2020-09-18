#include "common/common/base64.h"
#include "common/common/hex.h"

#include "extensions/tracers/skywalking/skywalking_types.h"

#include "test/extensions/tracers/skywalking/skywalking_test_helper.h"
#include "test/mocks/common.h"
#include "test/test_common/simulated_time_system.h"
#include "test/test_common/utility.h"

#include "gmock/gmock.h"
#include "gtest/gtest.h"

using namespace testing;

namespace Envoy {
namespace Extensions {
namespace Tracers {
namespace SkyWalking {

// Some constant strings for testing.
constexpr char TEST_SERVICE[] = "EnvoyIngressForTest";
constexpr char TEST_INSTANCE[] = "node-2.3.4.5~ingress";
constexpr char TEST_ADDRESS[] = "255.255.255.255";
constexpr char TEST_ENDPOINT[] = "/POST/path/for/test";

// Test whether SpanContext can correctly parse data from propagation headers and throw exceptions
// when errors occur.
TEST(SpanContextTest, SpanContextCommonTest) {
  NiceMock<Random::MockRandomGenerator> mock_random_generator;

  ON_CALL(mock_random_generator, random()).WillByDefault(Return(uint64_t(23333)));

  std::string trace_id = SkyWalkingTestHelper::generateId(mock_random_generator);
  std::string segment_id = SkyWalkingTestHelper::generateId(mock_random_generator);

  // Create properly formatted propagation headers and test whether the propagation headers can be
  // parsed correctly.
  std::string header_value_with_right_format =
      fmt::format("{}-{}-{}-{}-{}-{}-{}-{}", 0, SkyWalkingTestHelper::base64Encode(trace_id),
                  SkyWalkingTestHelper::base64Encode(segment_id), 233333,
                  SkyWalkingTestHelper::base64Encode(TEST_SERVICE),
                  SkyWalkingTestHelper::base64Encode(TEST_INSTANCE),
                  SkyWalkingTestHelper::base64Encode(TEST_ENDPOINT),
                  SkyWalkingTestHelper::base64Encode(TEST_ADDRESS));

  Http::TestRequestHeaderMapImpl headers_with_right_format{{"sw8", header_value_with_right_format}};

  auto previous_span_context = SpanContext::spanContextFromRequest(headers_with_right_format);
  EXPECT_NE(nullptr, previous_span_context.get());

  // Verify that each field parsed from the propagation headers is correct.
  EXPECT_EQ(previous_span_context->sampled_, 0);
  EXPECT_EQ(previous_span_context->trace_id_, trace_id);
  EXPECT_EQ(previous_span_context->trace_segment_id_, segment_id);
  EXPECT_EQ(previous_span_context->span_id_, 233333);
  EXPECT_EQ(previous_span_context->service_, TEST_SERVICE);
  EXPECT_EQ(previous_span_context->service_instance_, TEST_INSTANCE);
  EXPECT_EQ(previous_span_context->endpoint_, TEST_ENDPOINT);
  EXPECT_EQ(previous_span_context->target_address_, TEST_ADDRESS);

  // Test whether an exception can be correctly thrown when some fields are missing.
  std::string header_value_lost_some_parts =
      fmt::format("{}-{}-{}-{}-{}-{}", 0, SkyWalkingTestHelper::base64Encode(trace_id),
                  SkyWalkingTestHelper::base64Encode(segment_id), 3,
                  SkyWalkingTestHelper::base64Encode(TEST_SERVICE),
                  SkyWalkingTestHelper::base64Encode(TEST_INSTANCE));

  Http::TestRequestHeaderMapImpl headers_lost_some_parts{{"sw8", header_value_lost_some_parts}};

  EXPECT_THROW_WITH_MESSAGE(
      SpanContext::spanContextFromRequest(headers_lost_some_parts), EnvoyException,
      fmt::format("Invalid propagation header for SkyWalking: {}", header_value_lost_some_parts));

  // Test whether an exception can be correctly thrown when the sampling flag is wrong.
  Http::TestRequestHeaderMapImpl headers_with_error_sampled{
      {"sw8",
       fmt::format("{}-{}-{}-{}-{}-{}-{}-{}", 3, SkyWalkingTestHelper::base64Encode(trace_id),
                   SkyWalkingTestHelper::base64Encode(segment_id), 3,
                   SkyWalkingTestHelper::base64Encode(TEST_SERVICE),
                   SkyWalkingTestHelper::base64Encode(TEST_INSTANCE),
                   SkyWalkingTestHelper::base64Encode(TEST_ENDPOINT),
                   SkyWalkingTestHelper::base64Encode(TEST_ADDRESS))}};

  EXPECT_THROW_WITH_MESSAGE(SpanContext::spanContextFromRequest(headers_with_error_sampled),
                            EnvoyException,
                            "Invalid propagation header for SkyWalking: sampling flag can only be "
                            "'0' or '1' but '3' was provided");

  // Test whether an exception can be correctly thrown when the span id format is wrong.
  Http::TestRequestHeaderMapImpl headers_with_error_span_id{
      {"sw8",
       fmt::format("{}-{}-{}-{}-{}-{}-{}-{}", 1, SkyWalkingTestHelper::base64Encode(trace_id),
                   SkyWalkingTestHelper::base64Encode(segment_id), "abc",
                   SkyWalkingTestHelper::base64Encode(TEST_SERVICE),
                   SkyWalkingTestHelper::base64Encode(TEST_INSTANCE),
                   SkyWalkingTestHelper::base64Encode(TEST_ENDPOINT),
                   SkyWalkingTestHelper::base64Encode(TEST_ADDRESS))}};

  EXPECT_THROW_WITH_MESSAGE(
      SpanContext::spanContextFromRequest(headers_with_error_span_id), EnvoyException,
      "Invalid propagation header for SkyWalking: connot convert 'abc' to valid span id");

  // Test whether an exception can be correctly thrown when a field is empty.
  std::string header_value_with_empty_field =
      fmt::format("{}-{}-{}-{}-{}-{}-{}-{}", 1, SkyWalkingTestHelper::base64Encode(trace_id),
                  SkyWalkingTestHelper::base64Encode(segment_id), 4, "",
                  SkyWalkingTestHelper::base64Encode(TEST_INSTANCE),
                  SkyWalkingTestHelper::base64Encode(TEST_ENDPOINT),
                  SkyWalkingTestHelper::base64Encode(TEST_ADDRESS));
  Http::TestRequestHeaderMapImpl headers_with_empty_field{{"sw8", header_value_with_empty_field}};

  EXPECT_THROW_WITH_MESSAGE(
      SpanContext::spanContextFromRequest(headers_with_empty_field), EnvoyException,
      fmt::format("Invalid propagation header for SkyWalking: {}", header_value_with_empty_field));

  // Test whether an exception can be correctly thrown when a string is not properly encoded.
  Http::TestRequestHeaderMapImpl headers_with_error_field{
      {"sw8",
       fmt::format("{}-{}-{}-{}-{}-{}-{}-{}", 1, SkyWalkingTestHelper::base64Encode(trace_id),
                   SkyWalkingTestHelper::base64Encode(segment_id), 4, "hhhhhhh",
                   SkyWalkingTestHelper::base64Encode(TEST_INSTANCE),
                   SkyWalkingTestHelper::base64Encode(TEST_ENDPOINT),
                   SkyWalkingTestHelper::base64Encode(TEST_ADDRESS))}};

  EXPECT_THROW_WITH_MESSAGE(SpanContext::spanContextFromRequest(headers_with_error_field),
                            EnvoyException,
                            "Invalid propagation header for SkyWalking: parse error");
}

// Test whether the SegmentContext works normally when Envoy is the root node (Propagation headers
// does not exist).
TEST(SegmentContextTest, SegmentContextTestWithEmptyPreviousSpanContext) {
  NiceMock<Random::MockRandomGenerator> mock_random_generator;
  NiceMock<Envoy::MockTimeSystem> mock_time_source;

  ON_CALL(mock_random_generator, random()).WillByDefault(Return(233333));

  SegmentContextSharedPtr segment_context =
      SkyWalkingTestHelper::createSegmentContext(true, "NEW", "", mock_random_generator);

  // When previous span context is null, the value of the sampling flag depends on the tracing
  // decision
  EXPECT_EQ(segment_context->sampled(), 1);
  // The SegmentContext will use random generator to create new trace id and new trace segment id.
  EXPECT_EQ(segment_context->traceId(), SkyWalkingTestHelper::generateId(mock_random_generator));
  EXPECT_EQ(segment_context->traceSegmentId(),
            SkyWalkingTestHelper::generateId(mock_random_generator));

  EXPECT_EQ(segment_context->previousSpanContext(), nullptr);

  // Test whether the value of the fields can be set correctly and the value of the fields can be
  // obtained correctly.
  EXPECT_EQ(segment_context->endpoint(), "NEW#ENDPOINT");
  segment_context->setEndpoint(TEST_ENDPOINT);
  EXPECT_EQ(segment_context->endpoint(), TEST_ENDPOINT);

  EXPECT_EQ(segment_context->service(), "NEW#SERVICE");
  segment_context->setService(TEST_SERVICE);
  EXPECT_EQ(segment_context->service(), TEST_SERVICE);

  EXPECT_EQ(segment_context->serviceInstance(), "NEW#INSTANCE");
  segment_context->setServiceInstance(TEST_INSTANCE);
  EXPECT_EQ(segment_context->serviceInstance(), TEST_INSTANCE);

  // Test whether SegmentContext can correctly create SpanStore object with null parent SpanStore.
  SpanStore* root_span = SkyWalkingTestHelper::createSpanStore(segment_context.get(), nullptr,
                                                               "PARENT", mock_time_source);
  EXPECT_NE(nullptr, root_span);

  // The span id of the first SpanStore in each SegmentContext is 0. Its parent span id is -1.
  EXPECT_EQ(root_span->spanId(), 0);
  EXPECT_EQ(root_span->parentSpanId(), -1);

  // Verify that the SpanStore object is correctly stored in the SegmentContext.
  EXPECT_EQ(segment_context->spanList().size(), 1);
  EXPECT_EQ(segment_context->spanList()[0].get(), root_span);

  // Test whether SegmentContext can correctly create SpanStore object with a parent SpanStore.
  SpanStore* child_span = SkyWalkingTestHelper::createSpanStore(segment_context.get(), root_span,
                                                                "CHILD", mock_time_source);

  EXPECT_NE(nullptr, child_span);

  EXPECT_EQ(child_span->spanId(), 1);
  EXPECT_EQ(child_span->parentSpanId(), 0);

  EXPECT_EQ(segment_context->spanList().size(), 2);
  EXPECT_EQ(segment_context->spanList()[1].get(), child_span);
}

// Test whether the SegmentContext can work normally when a previous span context exists.
TEST(SegmentContextTest, SegmentContextTestWithPreviousSpanContext) {
  NiceMock<Random::MockRandomGenerator> mock_random_generator;

  ON_CALL(mock_random_generator, random()).WillByDefault(Return(23333));

  std::string trace_id = SkyWalkingTestHelper::generateId(mock_random_generator);
  std::string segment_id = SkyWalkingTestHelper::generateId(mock_random_generator);

  std::string header_value_with_right_format =
      fmt::format("{}-{}-{}-{}-{}-{}-{}-{}", 0, SkyWalkingTestHelper::base64Encode(trace_id),
                  SkyWalkingTestHelper::base64Encode(segment_id), 233333,
                  SkyWalkingTestHelper::base64Encode(TEST_SERVICE),
                  SkyWalkingTestHelper::base64Encode(TEST_INSTANCE),
                  SkyWalkingTestHelper::base64Encode(TEST_ENDPOINT),
                  SkyWalkingTestHelper::base64Encode(TEST_ADDRESS));

  Http::TestRequestHeaderMapImpl headers_with_right_format{{"sw8", header_value_with_right_format}};

  auto previous_span_context = SpanContext::spanContextFromRequest(headers_with_right_format);
  SpanContext* previous_span_context_bk = previous_span_context.get();

  Tracing::Decision decision;
  decision.traced = true;

  EXPECT_CALL(mock_random_generator, random()).WillRepeatedly(Return(666666));

  SegmentContext segment_context(std::move(previous_span_context), decision, mock_random_generator);

  // When a previous span context exists, the sampling flag of the SegmentContext depends on
  // previous span context rather than tracing decision.
  EXPECT_EQ(segment_context.sampled(), 0);

  // When previous span context exists, the trace id of SegmentContext remains the same as that of
  // previous span context.
  EXPECT_EQ(segment_context.traceId(), trace_id);
  // SegmentContext will always create a new trace segment id.
  EXPECT_NE(segment_context.traceSegmentId(), segment_id);

  EXPECT_EQ(segment_context.previousSpanContext(), previous_span_context_bk);
}

// Test whether SpanStore can work properly.
TEST(SpanStoreTest, SpanStoreCommonTest) {
  NiceMock<Random::MockRandomGenerator> mock_random_generator;
  NiceMock<Envoy::MockTimeSystem> mock_time_source;
  Event::SimulatedTimeSystem time_system;
  Envoy::SystemTime now = time_system.systemTime();

  ON_CALL(mock_random_generator, random()).WillByDefault(Return(23333));
  ON_CALL(mock_time_source, systemTime()).WillByDefault(Return(now));

  // Create segment context and first span store.
  SegmentContextSharedPtr segment_context =
      SkyWalkingTestHelper::createSegmentContext(true, "CURR", "PREV", mock_random_generator);
  SpanStore* root_store = SkyWalkingTestHelper::createSpanStore(segment_context.get(), nullptr,
                                                                "ROOT", mock_time_source);
  EXPECT_NE(nullptr, root_store);

  // The span id of the first SpanStore in each SegmentContext is 0. Its parent span id is -1.
  EXPECT_EQ(0, root_store->spanId());
  EXPECT_EQ(-1, root_store->parentSpanId());

  EXPECT_EQ(1, root_store->sampled());

  // Test whether the value of the fields can be set correctly and the value of the fields can be
  // obtained correctly.
  EXPECT_EQ(true, root_store->isEntrySpan());
  root_store->setAsEntrySpan(false);
  EXPECT_EQ(false, root_store->isEntrySpan());

  EXPECT_EQ(false, root_store->isError());
  root_store->setAsError(true);
  EXPECT_EQ(true, root_store->isError());

  EXPECT_EQ("ROOT#OPERATION", root_store->operation());
  root_store->setOperation("oooooop");
  EXPECT_EQ("oooooop", root_store->operation());
  root_store->setOperation("");
  // If the operation name is empty, the endpoint of the current SegmentContext will be used
  // instead.
  EXPECT_EQ("CURR#ENDPOINT", root_store->operation());

  EXPECT_EQ("0.0.0.0", root_store->peerAddress());
  root_store->setPeerAddress(TEST_ADDRESS);
  EXPECT_EQ(TEST_ADDRESS, root_store->peerAddress());

  EXPECT_EQ("0.0.0.0", root_store->upstreamAddress());
  root_store->setUpstreamAddress(TEST_ADDRESS);
  EXPECT_EQ(TEST_ADDRESS, root_store->upstreamAddress());

  EXPECT_EQ(22222222, root_store->startTime());
  root_store->setStartTime(23333);
  EXPECT_EQ(23333, root_store->startTime());

  EXPECT_EQ(33333333, root_store->endTime());
  root_store->setEndTime(25555);
  EXPECT_EQ(25555, root_store->endTime());

  EXPECT_EQ(-1, root_store->parentSpanId());
  root_store->setParentSpanId(234);
  EXPECT_EQ(234, root_store->parentSpanId());

  // When SpanStore calls finish, the end time will be set.
  root_store->finish();
  EXPECT_EQ(std::chrono::time_point_cast<std::chrono::milliseconds>(now).time_since_epoch().count(),
            root_store->endTime());

  // Test whether SpanStore can correctly inject propagation headers to request headers.

  Http::TestRequestHeaderMapImpl request_headers_with_upstream{{":authority", "test.com"}};
  root_store->injectContext(request_headers_with_upstream);

  std::string expected_header_value = fmt::format(
      "{}-{}-{}-{}-{}-{}-{}-{}", 1,
      SkyWalkingTestHelper::base64Encode(SkyWalkingTestHelper::generateId(mock_random_generator)),
      SkyWalkingTestHelper::base64Encode(SkyWalkingTestHelper::generateId(mock_random_generator)),
      0, SkyWalkingTestHelper::base64Encode("CURR#SERVICE"),
      SkyWalkingTestHelper::base64Encode("CURR#INSTANCE"),
      SkyWalkingTestHelper::base64Encode("CURR#ENDPOINT"),
      SkyWalkingTestHelper::base64Encode(TEST_ADDRESS));

  EXPECT_EQ(request_headers_with_upstream.get_("sw8"), expected_header_value);

  // Reset upstream address to empty.
  root_store->setUpstreamAddress("");

  // When the upstream address is empty, use the host in the request as the target address.
  Http::TestRequestHeaderMapImpl request_headers_no_upstream{{":authority", "test.com"}};
  root_store->injectContext(request_headers_no_upstream);
  expected_header_value = fmt::format(
      "{}-{}-{}-{}-{}-{}-{}-{}", 1,
      SkyWalkingTestHelper::base64Encode(SkyWalkingTestHelper::generateId(mock_random_generator)),
      SkyWalkingTestHelper::base64Encode(SkyWalkingTestHelper::generateId(mock_random_generator)),
      0, SkyWalkingTestHelper::base64Encode("CURR#SERVICE"),
      SkyWalkingTestHelper::base64Encode("CURR#INSTANCE"),
      SkyWalkingTestHelper::base64Encode("CURR#ENDPOINT"),
      SkyWalkingTestHelper::base64Encode("test.com"));

  EXPECT_EQ(request_headers_no_upstream.get_("sw8"), expected_header_value);
}

} // namespace SkyWalking
} // namespace Tracers
} // namespace Extensions
} // namespace Envoy
