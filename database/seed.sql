INSERT INTO customers VALUES
(1001,'John Smith (Demo)',745,120000,25,48,true),
(1002,'Mary Jones (Demo)',630,72000,42,8,false),
(1003,'David Lee (Demo)',690,95000,33,30,true) ON CONFLICT DO NOTHING;
INSERT INTO loan_applications(application_id,customer_id,amount,term_months) VALUES
('L001',1001,30000,36),('L002',1002,45000,60),('L003',1003,25000,48) ON CONFLICT DO NOTHING;
