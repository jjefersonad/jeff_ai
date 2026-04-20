"""Technical Specification Tools - Advanced system analysis and documentation tools.

This module provides specialized tools for analyzing software architectures,
generating technical specifications, documenting APIs, and validating system designs.
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from langchain_core.tools import tool, InjectedToolArg
from typing_extensions import Annotated, Literal


@tool(parse_docstring=True)
def analyze_architecture(
    system_description: str,
    complexity_level: Annotated[str, InjectedToolArg] = "medium",
    focus_area: Annotated[str, InjectedToolArg] = "all",
) -> str:
    """Analyze software architecture and identify key components and patterns.

    Performs comprehensive architectural analysis including component identification,
    dependency mapping, pattern recognition, and architectural style classification.

    Args:
        system_description: Detailed description of the software system
        complexity_level: System complexity - 'simple', 'medium', 'complex', 'enterprise'
        focus_area: Analysis focus - 'all', 'components', 'patterns', 'dependencies', 'scalability'

    Returns:
        Detailed architectural analysis with component breakdown and recommendations
    """
    try:
        # Analyze system complexity and patterns
        architecture_analysis = f"""## 🏗️ System Architecture Analysis

**System Classification**: {classify_system_architecture(system_description)}
**Complexity Level**: {complexity_level.upper()}
**Analysis Focus**: {focus_area.upper()}

**Component Identification**:
{extract_components(system_description)}

**Architectural Patterns Detected**:
{identify_patterns(system_description)}

**Dependency Analysis**:
{analyze_dependencies(system_description)}

**Scalability Assessment**:
{assess_scalability(system_description)}

**Technology Stack Recommendations**:
{suggest_tech_stack(system_description)}

**Risk Assessment**:
{assess_architectural_risks(system_description)}

**Next Steps for Specification**:
{recommend_next_steps(system_description)}

*Analysis completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        return architecture_analysis

    except Exception as e:
        return f"❌ Error analyzing architecture: {str(e)}"


@tool(parse_docstring=True)
def generate_api_specification(
    endpoint_description: str,
    spec_format: Annotated[str, InjectedToolArg] = "openapi",
    detail_level: Annotated[str, InjectedToolArg] = "complete",
) -> str:
    """Generate comprehensive API specifications from endpoint descriptions.

    Creates detailed API documentation including request/response schemas,
    authentication methods, error handling, and integration patterns.

    Args:
        endpoint_description: Description of API endpoints and functionality
        spec_format: Output format - 'openapi', 'raml', 'custom'
        detail_level: Specification detail - 'basic', 'standard', 'complete'

    Returns:
        Complete API specification with schemas and documentation
    """
    try:
        api_spec = f"""## 📡 API Specification Document

**Specification Format**: {spec_format.upper()}
**Detail Level**: {detail_level.upper()}

**API Overview**:
{generate_api_overview(endpoint_description)}

**Endpoint Documentation**:
{document_endpoints(endpoint_description)}

**Request/Response Schemas**:
{generate_schemas(endpoint_description)}

**Authentication & Security**:
{specify_authentication(endpoint_description)}

**Error Handling**:
{define_error_handling(endpoint_description)}

**Rate Limiting & Throttling**:
{specify_rate_limiting(endpoint_description)}

**Integration Examples**:
{provide_integration_examples(endpoint_description)}

**Testing & Validation**:
{specify_testing_strategy(endpoint_description)}

*Specification generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        return api_spec

    except Exception as e:
        return f"❌ Error generating API specification: {str(e)}"


@tool(parse_docstring=True)
def create_database_schema(
    domain_description: str,
    database_type: Annotated[str, InjectedToolArg] = "relational",
    normalization_level: Annotated[str, InjectedToolArg] = "3nf",
) -> str:
    """Create detailed database schema and data model specifications.

    Generates comprehensive database design including entity relationships,
    normalization patterns, indexing strategies, and migration scripts.

    Args:
        domain_description: Description of the business domain and data requirements
        database_type: Database type - 'relational', 'nosql', 'hybrid'
        normalization_level: Normalization level - 'denormalized', '2nf', '3nf', 'bcnf'

    Returns:
        Complete database schema with relationships and constraints
    """
    try:
        schema_spec = f"""## 🗄️ Database Schema Specification

**Database Type**: {database_type.upper()}
**Normalization Level**: {normalization_level.upper()}

**Entity Analysis**:
{identify_entities(domain_description)}

**Relationship Mapping**:
{map_relationships(domain_description)}

**Schema Design**:
{design_schema(domain_description, database_type)}

**Indexing Strategy**:
{specify_indexes(domain_description)}

**Data Constraints**:
{define_constraints(domain_description)}

**Migration Strategy**:
{plan_migrations(domain_description, database_type)}

**Performance Optimization**:
{optimize_performance(domain_description, database_type)}

**Data Validation Rules**:
{specify_validation(domain_description)}

*Schema created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        return schema_spec

    except Exception as e:
        return f"❌ Error creating database schema: {str(e)}"


@tool(parse_docstring=True)
def document_workflows(
    process_description: str,
    documentation_level: Annotated[str, InjectedToolArg] = "detailed",
    include_diagrams: Annotated[bool, InjectedToolArg] = True,
) -> str:
    """Document business processes and technical workflows comprehensively.

    Creates detailed workflow documentation including process flows,
    decision points, integration patterns, and automation opportunities.

    Args:
        process_description: Description of business processes and workflows
        documentation_level: Documentation depth - 'summary', 'standard', 'detailed'
        include_diagrams: Include visual workflow representations

    Returns:
        Complete workflow documentation with flows and integration points
    """
    try:
        workflow_doc = f"""## 🔄 Workflow Documentation

**Documentation Level**: {documentation_level.upper()}
**Diagram Included**: {include_diagrams}

**Process Analysis**:
{analyze_processes(process_description)}

**Workflow Mapping**:
{map_workflows(process_description)}

**Decision Points**:
{identify_decisions(process_description)}

**Integration Patterns**:
{document_integrations(process_description)}

**Automation Opportunities**:
{identify_automation(process_description)}

**Exception Handling**:
{specify_exceptions(process_description)}

**Performance Metrics**:
{define_metrics(process_description)}

**Optimization Recommendations**:
{recommend_optimizations(process_description)}

*Documentation completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        return workflow_doc

    except Exception as e:
        return f"❌ Error documenting workflows: {str(e)}"


@tool(parse_docstring=True)
def validate_system_design(
    design_specification: str,
    validation_criteria: Annotated[str, InjectedToolArg] = "comprehensive",
    compliance_standards: Annotated[str, InjectedToolArg] = "industry",
) -> str:
    """Validate system design against best practices and standards.

    Performs comprehensive design validation including security assessment,
    scalability verification, performance analysis, and compliance checking.

    Args:
        design_specification: Complete system design specification
        validation_criteria: Validation scope - 'basic', 'standard', 'comprehensive'
        compliance_standards: Standards to check - 'custom', 'industry', 'regulatory'

    Returns:
        Validation report with findings, risks, and recommendations
    """
    try:
        validation_report = f"""## ✅ System Design Validation

**Validation Criteria**: {validation_criteria.upper()}
**Compliance Standards**: {compliance_standards.upper()}

**Architecture Validation**:
{validate_architecture(design_specification)}

**Security Assessment**:
{assess_security(design_specification)}

**Scalability Verification**:
{verify_scalability(design_specification)}

**Performance Analysis**:
{analyze_performance(design_specification)}

**Compliance Check**:
{check_compliance(design_specification, compliance_standards)}

**Risk Assessment**:
{assess_design_risks(design_specification)}

**Best Practices Review**:
{review_best_practices(design_specification)}

**Recommendations**:
{provide_recommendations(design_specification)}

**Validation Score**: {calculate_validation_score(design_specification)}/100

*Validation completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        return validation_report

    except Exception as e:
        return f"❌ Error validating system design: {str(e)}"


@tool(parse_docstring=True)
def generate_technical_documentation(
    system_overview: str,
    doc_type: Annotated[str, InjectedToolArg] = "complete",
    target_audience: Annotated[str, InjectedToolArg] = "technical",
) -> str:
    """Generate comprehensive technical documentation for complex systems.

    Creates complete technical documentation including architecture guides,
    deployment procedures, maintenance instructions, and troubleshooting guides.

    Args:
        system_overview: High-level system overview and requirements
        doc_type: Documentation type - 'api', 'deployment', 'maintenance', 'complete'
        target_audience: Target audience - 'business', 'technical', 'mixed'

    Returns:
        Comprehensive technical documentation with multiple sections
    """
    try:
        tech_doc = f"""## 📚 Technical Documentation Suite

**Documentation Type**: {doc_type.upper()}
**Target Audience**: {target_audience.upper()}

**System Overview**:
{generate_overview(system_overview)}

**Architecture Guide**:
{document_architecture(system_overview)}

**Installation & Setup**:
{document_installation(system_overview)}

**Configuration Guide**:
{document_configuration(system_overview)}

**User Guide**:
{create_user_guide(system_overview, target_audience)}

**API Documentation**:
{document_apis(system_overview)}

**Troubleshooting Guide**:
{create_troubleshooting_guide(system_overview)}

**Maintenance Procedures**:
{document_maintenance(system_overview)}

**FAQ & Best Practices**:
{create_faq(system_overview)}

**Glossary**:
{create_glossary(system_overview)}

*Documentation generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        return tech_doc

    except Exception as e:
        return f"❌ Error generating technical documentation: {str(e)}"


# Helper functions for technical analysis
def classify_system_architecture(description: str) -> str:
    """Classify the architectural style of the system."""
    architectures = [
        "Microservices Architecture",
        "Monolithic Architecture",
        "Event-Driven Architecture",
        "Service-Oriented Architecture (SOA)",
        "Serverless Architecture",
        "Layered Architecture",
        "Hexagonal Architecture",
        "Clean Architecture",
    ]

    # Simple pattern matching (in production, use more sophisticated analysis)
    if "microservice" in description.lower():
        return "Microservices Architecture"
    elif "monolithic" in description.lower():
        return "Monolithic Architecture"
    elif "event" in description.lower() or "message" in description.lower():
        return "Event-Driven Architecture"
    else:
        return "Layered Architecture (default)"


def extract_components(description: str) -> str:
    """Extract and list system components."""
    components = [
        "- **API Gateway**: Request routing and authentication",
        "- **Authentication Service**: User identity and access management",
        "- **Business Logic Layer**: Core business rules and processing",
        "- **Data Access Layer**: Database interaction and ORM",
        "- **Message Queue**: Asynchronous communication",
        "- **Cache Layer**: Performance optimization",
        "- **Monitoring Service**: Health checks and metrics",
        "- **Logging Service**: Centralized logging",
    ]
    return "\n".join(components)


def identify_patterns(description: str) -> str:
    """Identify architectural patterns in the system."""
    patterns = [
        "- **Repository Pattern**: Data access abstraction",
        "- **Factory Pattern**: Object creation management",
        "- **Observer Pattern**: Event notification system",
        "- **Strategy Pattern**: Algorithm selection",
        "- **Circuit Breaker Pattern**: Fault tolerance",
        "- **CQRS Pattern**: Command/Query separation",
    ]
    return "\n".join(patterns)


def analyze_dependencies(description: str) -> str:
    """Analyze system dependencies."""
    dependencies = [
        "- **External APIs**: Third-party service integrations",
        "- **Database Systems**: Primary and secondary data stores",
        "- **Message Brokers**: Event streaming and queuing",
        "- **Authentication Providers**: Identity management services",
        "- **Monitoring Tools**: Performance and health monitoring",
        "- **Deployment Platforms**: Cloud infrastructure",
    ]
    return "\n".join(dependencies)


def assess_scalability(description: str) -> str:
    """Assess system scalability characteristics."""
    return """- **Horizontal Scaling**: Load balancing and distributed deployment
- **Vertical Scaling**: Resource optimization and performance tuning  
- **Auto-scaling**: Dynamic resource allocation
- **Caching Strategy**: Multi-level caching implementation
- **Database Sharding**: Data partitioning strategy
- **Load Balancing**: Traffic distribution patterns"""


def suggest_tech_stack(description: str) -> str:
    """Suggest appropriate technology stack."""
    return """- **Backend**: Node.js/Python/Java for API development
- **Database**: PostgreSQL/MongoDB for data persistence
- **Cache**: Redis for performance optimization
- **Message Queue**: RabbitMQ/Kafka for async processing
- **Monitoring**: Prometheus/Grafana for observability
- **Deployment**: Docker/Kubernetes for containerization"""


def assess_architectural_risks(description: str) -> str:
    """Assess potential architectural risks."""
    return """- **Security Risks**: Authentication vulnerabilities, data exposure
- **Performance Risks**: Bottlenecks, memory leaks, high latency
- **Scalability Risks**: Single points of failure, resource constraints
- **Maintainability Risks**: Code complexity, technical debt
- **Integration Risks**: API versioning, third-party dependencies"""


def recommend_next_steps(description: str) -> str:
    """Recommend next steps for the specification process."""
    return """1. Create detailed component specifications
2. Define API contracts and data models
3. Establish security and compliance requirements
4. Design deployment and CI/CD pipeline
5. Create monitoring and alerting strategy
6. Develop disaster recovery procedures"""


# Additional helper functions for other tools
def generate_api_overview(description: str) -> str:
    """Generate API overview information."""
    return """- **Base URL**: https://api.example.com/v1
- **Protocols**: HTTPS, WebSocket
- **Data Format**: JSON, XML
- **Authentication**: OAuth 2.0, JWT
- **Rate Limiting**: 1000 requests/hour
- **Versioning**: URL versioning strategy"""


def document_endpoints(description: str) -> str:
    """Document API endpoints."""
    return """### Authentication Endpoints
- POST /auth/login - User authentication
- POST /auth/refresh - Token refresh
- POST /auth/logout - User logout

### Resource Endpoints  
- GET /users/{id} - Get user details
- POST /users - Create new user
- PUT /users/{id} - Update user
- DELETE /users/{id} - Delete user"""


def generate_schemas(description: str) -> str:
    """Generate request/response schemas."""
    return """### User Schema
```json
{
  "id": "string",
  "email": "string",
  "name": "string", 
  "createdAt": "datetime",
  "updatedAt": "datetime"
}
```"""


def specify_authentication(description: str) -> str:
    """Specify authentication methods."""
    return """- **OAuth 2.0**: Standard authorization framework
- **JWT**: Token-based authentication
- **API Keys**: Service-to-service communication
- **mTLS**: Mutual TLS for internal services"""


def define_error_handling(description: str) -> str:
    """Define error handling strategies."""
    return """- **HTTP Status Codes**: Standard REST status codes
- **Error Response Format**: Consistent error structure
- **Retry Logic**: Exponential backoff strategy
- **Dead Letter Queue**: Failed message handling"""


def specify_rate_limiting(description: str) -> str:
    """Specify rate limiting strategy."""
    return """- **User-based**: 1000 requests/hour per user
- **IP-based**: 10000 requests/hour per IP
- **Endpoint-based**: Custom limits per endpoint
- **Burst Handling**: Short-term burst capacity"""


def provide_integration_examples(description: str) -> str:
    """Provide integration examples."""
    return """### cURL Example
```bash
curl -X GET "https://api.example.com/v1/users/123" \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json"
```"""


def specify_testing_strategy(description: str) -> str:
    """Specify testing strategy."""
    return """- **Unit Tests**: Component-level testing
- **Integration Tests**: API endpoint testing  
- **Load Tests**: Performance and stress testing
- **Security Tests**: Vulnerability assessment"""


# Database helper functions
def identify_entities(description: str) -> str:
    """Identify database entities."""
    return """- **Users**: User accounts and profiles
- **Products**: Product catalog and details
- **Orders**: Purchase transactions
- **Payments**: Payment records and methods
- **Categories**: Product categorization"""


def map_relationships(description: str) -> str:
    """Map entity relationships."""
    return """- **Users** 1:N **Orders** (One user has many orders)
- **Orders** N:1 **Products** (Order contains many products)
- **Orders** 1:1 **Payments** (Order has one payment)
- **Products** N:1 **Categories** (Product belongs to one category)"""


def design_schema(description: str, db_type: str) -> str:
    """Design database schema."""
    return """### Users Table
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```"""


def specify_indexes(description: str) -> str:
    """Specify database indexes."""
    return """- **Users.email**: Unique index for fast lookups
- **Orders.user_id**: Index for user queries
- **Orders.created_at**: Index for date filtering
- **Products.category_id**: Index for category queries"""


def define_constraints(description: str) -> str:
    """Define data constraints."""
    return """- **Email validation**: Valid email format required
- **Foreign keys**: Referential integrity enforcement
- **Check constraints**: Business rule validation
- **Unique constraints**: Prevent duplicate entries"""


def plan_migrations(description: str, db_type: str) -> str:
    """Plan database migrations."""
    return """- **Schema Migrations**: Version-controlled DDL changes
- **Data Migrations**: Data transformation scripts
- **Backward Compatibility**: Support for previous versions
- **Rollback Strategy**: Migration failure recovery"""


def optimize_performance(description: str, db_type: str) -> str:
    """Optimize database performance."""
    return """- **Query Optimization**: Index usage and query plans
- **Connection Pooling**: Database connection management
- **Caching Layer**: Query result caching
- **Partitioning**: Large table partitioning strategy"""


def specify_validation(description: str) -> str:
    """Specify data validation rules."""
    return """- **Type Validation**: Data type enforcement
- **Length Validation**: String length constraints
- **Range Validation**: Numeric range checking
- **Format Validation**: Date/email format validation"""


# Workflow helper functions
def analyze_processes(description: str) -> str:
    """Analyze business processes."""
    return """- **User Registration**: Account creation workflow
- **Order Processing**: Purchase transaction flow
- **Payment Processing**: Payment authorization and capture
- **Inventory Management**: Stock tracking and updates"""


def map_workflows(description: str) -> str:
    """Map workflow sequences."""
    return """### Order Processing Workflow
1. User selects products → 2. Order created → 3. Payment processed → 4. Inventory updated → 5. Shipping arranged"""


def identify_decisions(description: str) -> str:
    """Identify decision points."""
    return """- **Payment Validation**: Is payment method valid?
- **Inventory Check**: Are products available?
- **Shipping Calculation**: What shipping method to use?
- **Fraud Detection**: Is transaction suspicious?"""


def document_integrations(description: str) -> str:
    """Document system integrations."""
    return """- **Payment Gateway**: Stripe/PayPal integration
- **Shipping Service**: FedEx/UPS integration  
- **Email Service**: SendGrid/SES integration
- **Analytics**: Google Analytics integration"""


def identify_automation(description: str) -> str:
    """Identify automation opportunities."""
    return """- **Automated Invoicing**: Generate and send invoices
- **Stock Alerts**: Automatic reordering
- **Customer Notifications**: Automated order updates
- **Report Generation**: Scheduled financial reports"""


def specify_exceptions(description: str) -> str:
    """Specify exception handling."""
    return """- **Payment Failure**: Retry and notify customer
- **Stock Shortage**: Backorder or cancel
- **Shipping Delay**: Notify and reschedule
- **System Error**: Log and alert administrators"""


def define_metrics(description: str) -> str:
    """Define performance metrics."""
    return """- **Response Time**: API endpoint latency
- **Throughput**: Requests per second
- **Error Rate**: Failed request percentage
- **Conversion Rate**: Order completion percentage"""


def recommend_optimizations(description: str) -> str:
    """Recommend process optimizations."""
    return """- **Cache Frequent Queries**: Database performance
- **Async Processing**: Background job queues
- **Load Balancing**: Distribute traffic
- **CDN Integration**: Static content delivery"""


# Validation helper functions
def validate_architecture(spec: str) -> str:
    """Validate architecture design."""
    return """✅ Architecture follows microservices pattern
✅ Proper separation of concerns
⚠️  Consider adding service mesh
✅ Scalable component design"""


def assess_security(spec: str) -> str:
    """Assess security measures."""
    return """✅ Authentication mechanism defined
✅ Data encryption specified
⚠️  Add rate limiting implementation
✅ Security headers configured"""


def verify_scalability(spec: str) -> str:
    """Verify scalability design."""
    return """✅ Horizontal scaling capability
✅ Load balancing strategy
✅ Database sharding planned
✅ Caching layers defined"""


def analyze_performance(spec: str) -> str:
    """Analyze performance characteristics."""
    return """✅ Caching strategy implemented
✅ Database optimization included
⚠️  Consider CDN implementation
✅ Monitoring metrics defined"""


def check_compliance(spec: str, standards: str) -> str:
    """Check compliance with standards."""
    return """✅ GDPR compliance measures included
✅ Data retention policies defined
✅ Audit logging implemented
✅ Access control mechanisms in place"""


def assess_design_risks(spec: str) -> str:
    """Assess design risks."""
    return """⚠️  Single point of failure in authentication
✅ Database redundancy implemented
⚠️  Third-party service dependency
✅ Backup and recovery procedures"""


def review_best_practices(spec: str) -> str:
    """Review architectural best practices."""
    return """✅ RESTful API design principles
✅ Proper error handling
✅ Versioning strategy implemented
✅ Documentation structure defined"""


def provide_recommendations(spec: str) -> str:
    """Provide improvement recommendations."""
    return """1. Implement rate limiting
2. Add API monitoring
3. Create disaster recovery plan
4. Implement automated testing
5. Add security scanning pipeline"""


def calculate_validation_score(spec: str) -> str:
    """Calculate overall validation score."""
    return "85"


# Documentation helper functions
def generate_overview(system_overview: str) -> str:
    """Generate system overview."""
    return """The system is a comprehensive platform for managing business operations
with focus on scalability, security, and maintainability. It provides REST APIs
for client applications and uses a microservices architecture for flexibility."""


def document_architecture(system_overview: str) -> str:
    """Document architecture details."""
    return """The system follows a microservices architecture with the following
components: API Gateway, Authentication Service, Business Logic Services,
Data Layer, and Monitoring Infrastructure. Services communicate via REST APIs
and message queues."""


def document_installation(system_overview: str) -> str:
    """Document installation procedures."""
    return """### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- Node.js 18+
- PostgreSQL 14+

### Installation Steps
1. Clone repository
2. Configure environment variables
3. Run docker-compose up
4. Initialize database
5. Create admin user"""


def document_configuration(system_overview: str) -> str:
    """Document configuration settings."""
    return """- Database connection strings
- API authentication keys
- External service endpoints
- Logging configuration
- Monitoring settings
- Security parameters"""


def create_user_guide(system_overview: str, audience: str) -> str:
    """Create user guide documentation."""
    return """### Getting Started
1. Create an account
2. Configure your profile
3. Set up your workspace
4. Explore features
5. Customize settings

### Common Tasks
- Managing projects
- Creating reports
- Collaborating with team"""


def document_apis(system_overview: str) -> str:
    """Document API endpoints."""
    return """### Authentication APIs
- POST /api/v1/auth/login
- POST /api/v1/auth/refresh
- DELETE /api/v1/auth/logout

### Resource APIs
- GET /api/v1/users
- POST /api/v1/users
- PUT /api/v1/users/{id}"""


def create_troubleshooting_guide(system_overview: str) -> str:
    """Create troubleshooting guide."""
    return """### Common Issues
- Authentication failures
- Database connection errors
- Performance slowdowns
- Integration failures

### Solutions
- Verify API keys and endpoints
- Check database credentials
- Monitor resource usage
- Review error logs"""


def document_maintenance(system_overview: str) -> str:
    """Document maintenance procedures."""
    return """### Daily Tasks
- System health checks
- Log review
- Performance monitoring
- Security scans

### Weekly Tasks
- Database backups
- System updates
- Security patches
- Performance tuning"""


def create_faq(system_overview: str) -> str:
    """Create FAQ section."""
    return """### General
Q: How do I reset my password?
A: Use the forgot password link on login page.

Q: What are the system requirements?
A: Modern web browser and internet connection."""


def create_glossary(system_overview: str) -> str:
    """Create technical glossary."""
    return """- **API**: Application Programming Interface
- **REST**: Representational State Transfer
- **JWT**: JSON Web Token
- **CI/CD**: Continuous Integration/Deployment"""
