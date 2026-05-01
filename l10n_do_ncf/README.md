# Fiscal Accounting (Rep. Dominicana) - NCF Management

This module implements the administration and management of fiscal receipt numbers (NCF) for compliance with norm 06-18 of the Dominican Republic Internal Revenue Service.

## 📌 Description

The **Fiscal Accounting** module for Odoo 18 provides comprehensive management of NCF (Números de Comprobantes Fiscales) as required by Dominican Republic law. This module ensures full compliance with DGII (Dirección General de Impuestos Internos) regulations for fiscal documentation and electronic invoicing.

## ✅ Features

### 🧾 NCF Management
- **Automatic NCF Generation**: Automatic assignment of fiscal numbers to invoices
- **NCF Sequence Control**: Pre-configured sequences for all NCF types
- **Real-time Validation**: Validation of NCF structure and format
- **DGII Integration**: Real-time validation with DGII web services

### 📝 NCF Types Supported
- **01**: Fiscal Credit (Tax Credit Invoice)
- **02**: Consumer Invoice (Final Consumer)
- **03**: Fiscal Debit Note
- **04**: Fiscal Credit Note  
- **11**: Informal Supplier Invoice
- **12**: Single Entry Record
- **13**: Minor Expenses
- **14**: Special Regime
- **15**: Governmental
- **16**: Export Invoice
- **17**: External Payments

### 🔄 Fiscal Sequences
- **Pre-configured Sequences**: Ready-to-use sequences for all NCF types
- **Automatic Numbering**: Intelligent assignment based on transaction type
- **Sequence Validation**: Ensures sequential numbering as required by law
- **Expiration Control**: Monitoring of sequence authorization expiration dates

### 🌐 DGII Web Service Integration
- **NCF-RNC Validation**: Real-time validation of NCF against RNC
- **Status Verification**: Check NCF status (valid, cancelled, expired)
- **Automatic Updates**: Periodic validation of issued NCFs
- **Error Handling**: Comprehensive error management and logging

### 💱 Currency and Exchange Rate Management
- **Multi-currency Support**: Handle transactions in USD and DOP
- **Central Bank Rates**: Automatic import of official exchange rates
- **Historical Rates**: Maintain exchange rate history for reporting
- **Rate Validation**: Ensure compliance with fiscal requirements

### 👥 Customer and Supplier Management
- **RNC/Cedula Validation**: Validate tax identification numbers
- **Fiscal Classification**: Automatic classification of business partners
- **DGII Lookup**: Retrieve partner information from DGII database
- **Address Validation**: Validate business addresses against official records

## 🔧 Technical Features

### Models Enhanced
- `account.move`: Extended with NCF fields and validation
- `account.journal`: Enhanced with NCF sequence configuration
- `res.partner`: Extended with fiscal information fields
- `account.tax`: Enhanced with DGII tax classifications

### Security Features
- **Access Control**: Role-based access to fiscal operations
- **Audit Trail**: Complete logging of all fiscal operations
- **Data Integrity**: Built-in validations to prevent data corruption
- **Backup Integration**: Automatic backup of critical fiscal data

### Automation Features
- **Scheduled Jobs**: Automatic validation and updates via cron jobs
- **Email Notifications**: Alerts for sequence expiration and errors
- **Batch Processing**: Efficient handling of large volumes of transactions
- **Report Generation**: Automated generation of compliance reports

## 📥 Requirements

- **Odoo Version**: 18.0+
- **Dependencies**:
  - `base`: Odoo core functionality
  - `web`: Web interface
  - `account`: Accounting module
  - `l10n_do`: Dominican Republic localization base

## 🚀 Installation

1. Install the Dominican Republic localization (`l10n_do`)
2. Copy this module to your Odoo addons directory
3. Update the application list
4. Install the "Fiscal Accounting (Rep. Dominicana)" module
5. Configure your company's fiscal information
6. Set up NCF sequences in journals

## 💼 Usage

### Initial Configuration

1. **Company Setup**:
   - Configure company RNC
   - Set fiscal address
   - Configure fiscal year settings

2. **Journal Configuration**:
   - Assign NCF sequences to sales journals
   - Configure purchase journals for fiscal validation
   - Set up default NCF types per journal

3. **Partner Configuration**:
   - Configure customers with RNC/Cedula
   - Set fiscal classification (Person/Company)
   - Validate addresses and contact information

### Daily Operations

1. **Creating Invoices**:
   - NCF is automatically assigned based on journal configuration
   - Real-time validation with DGII services
   - Automatic fiscal classification based on customer type

2. **Validating NCFs**:
   - Manual validation available in invoice form
   - Batch validation through dedicated wizard
   - Automatic validation via scheduled jobs

3. **Managing Sequences**:
   - Monitor sequence usage and remaining numbers
   - Request new sequences from DGII when needed
   - Handle sequence expiration and renewal

### Reporting and Compliance

1. **Fiscal Reports**:
   - Generate required DGII reports
   - Export data in official formats
   - Validate report data against source documents

2. **Audit and Control**:
   - Review NCF assignment log
   - Validate sequence integrity
   - Monitor compliance status

## 🔍 Validation Rules

### NCF Format Validation
- Proper NCF structure (B01XXXXXXXX)
- Valid checksum calculation
- Sequence number validation
- Expiration date verification

### Business Rules
- Customer type vs NCF type compatibility
- Tax calculation validation
- Required fields completion
- DGII service response validation

## ⚙️ Configuration Parameters

The module includes several configuration parameters:
- DGII service endpoints
- Validation timeouts
- Automatic validation schedules
- Error handling preferences

## 📞 Support

- **Version**: 18.0.2.2.9
- **License**: LGPL-3
- **Authors**: Marcos, Guavana, Indexa, Iterativo SRL, Neotec, Jenrax SRL
- **Website**: https://github.com/Jenrax-git/l10n-do

For technical support, customizations, or implementation assistance, please contact the development team.
