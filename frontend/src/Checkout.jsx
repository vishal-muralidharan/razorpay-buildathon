import { useState, useEffect } from "react";
import { api } from "./api";
import { Link } from "react-router-dom";

export default function Checkout() {
  const [formData, setFormData] = useState({ name: "Demo User", phone: "9876543210", email: "demo@example.com" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [simulating, setSimulating] = useState(false);

  useEffect(() => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    document.body.appendChild(script);
    return () => {
      document.body.removeChild(script);
    };
  }, []);

  const handleChange = (e) => setFormData({ ...formData, [e.target.name]: e.target.value });

  const handleSuccess = async (response, customer_id, razorpay_customer_id) => {
    try {
      await api.verifyRegistration({
        customer_id,
        razorpay_customer_id,
        razorpay_payment_id: response.razorpay_payment_id,
        razorpay_order_id: response.razorpay_order_id,
        razorpay_signature: response.razorpay_signature,
      });
      setSuccess(true);
    } catch (err) {
      setError("Verification failed: " + err.message);
    } finally {
      setLoading(false);
      setSimulating(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      const custResp = await api.createCustomer(formData);
      const { customer_id, razorpay_customer_id } = custResp;

      const orderResp = await api.createOrder({ customer_id, razorpay_customer_id });
      const { order_id, amount, currency } = orderResp;

      if (order_id.startsWith("order_SIM")) {
        setSimulating(true);
        setTimeout(() => {
          handleSuccess({
            razorpay_payment_id: "pay_SIM" + Math.random().toString(36).substr(2, 9),
            razorpay_order_id: order_id,
            razorpay_signature: "simulated_signature",
          }, customer_id, razorpay_customer_id);
        }, 2000);
        return;
      }

      const options = {
        key: import.meta.env.VITE_RAZORPAY_KEY_ID || "",
        amount: amount * 100,
        currency: currency,
        name: "Vela SaaS",
        description: "Monthly Subscription Mandate",
        order_id: order_id,
        customer_id: razorpay_customer_id,
        recurring: true,
        handler: function (response) {
          handleSuccess(response, customer_id, razorpay_customer_id);
        },
        prefill: {
          name: formData.name,
          email: formData.email,
          contact: formData.phone,
        },
        theme: {
          color: "#0D94FB",
        },
      };

      if (!window.Razorpay) {
        throw new Error("Razorpay SDK not loaded");
      }

      const rzp = new window.Razorpay(options);
      rzp.on('payment.failed', function (response){
        setError("Payment failed: " + response.error.description);
        setLoading(false);
      });
      rzp.open();
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-rzp-gray flex items-center justify-center p-6 font-body">
        <div className="bg-white max-w-md w-full rounded-2xl shadow-xl p-8 text-center border border-rzp-border transform transition-all hover:scale-[1.02]">
          <div className="w-16 h-16 bg-status-success_bg rounded-full flex items-center justify-center mx-auto mb-6">
            <svg className="w-8 h-8 text-status-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-2xl font-display font-bold text-rzp-navy mb-2">Mandate Active</h2>
          <p className="text-gray-500 mb-8 leading-relaxed">
            Your UPI Autopay mandate has been successfully registered. You will be billed monthly.
          </p>
          <Link to="/" className="inline-block bg-rzp-blue hover:bg-blue-600 text-white font-medium py-3 px-8 rounded-lg transition-colors shadow-lg shadow-blue-500/30">
            Go to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-rzp-gray flex items-center justify-center p-6 font-body relative">
      {simulating && (
        <div className="absolute inset-0 z-50 bg-white/80 backdrop-blur-sm flex flex-col items-center justify-center transition-opacity">
          <div className="w-12 h-12 border-4 border-rzp-blue border-t-transparent rounded-full animate-spin mb-4"></div>
          <p className="text-lg font-medium text-rzp-navy font-display animate-pulse">
            Simulating Razorpay UPI Mandate...
          </p>
        </div>
      )}
      
      <div className="w-full max-w-4xl grid md:grid-cols-2 bg-white rounded-2xl shadow-xl overflow-hidden border border-rzp-border">
        {/* Left Side - Info */}
        <div className="bg-rzp-navy p-10 text-white flex flex-col justify-center relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-blue-600/20 to-transparent"></div>
          <div className="relative z-10">
            <h1 className="text-3xl font-display font-bold mb-4 leading-tight">
              Set up your <span className="text-rzp-blue">UPI Autopay</span> mandate
            </h1>
            <p className="text-blue-100 mb-8 opacity-90 leading-relaxed">
              Experience seamless monthly billing with automated retries. Your payments are secured by Razorpay and NPCI guidelines.
            </p>
            <div className="space-y-4 text-sm font-medium">
              <div className="flex items-center space-x-3">
                <div className="w-6 h-6 rounded-full bg-white/10 flex items-center justify-center">✓</div>
                <span>₹1 initial setup charge (Refunded)</span>
              </div>
              <div className="flex items-center space-x-3">
                <div className="w-6 h-6 rounded-full bg-white/10 flex items-center justify-center">✓</div>
                <span>Cancel anytime</span>
              </div>
              <div className="flex items-center space-x-3">
                <div className="w-6 h-6 rounded-full bg-white/10 flex items-center justify-center">✓</div>
                <span>NPCI compliant retries</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Side - Form */}
        <div className="p-10 flex flex-col justify-center">
          <div className="flex justify-between items-center mb-8">
            <h2 className="text-2xl font-display font-bold text-rzp-navy">Customer Details</h2>
            <Link to="/" className="text-sm font-medium text-gray-400 hover:text-rzp-navy transition-colors">
              Skip to Dashboard
            </Link>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-status-error_bg border border-status-error/20 text-status-error rounded-lg text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">Full Name</label>
              <input 
                type="text" name="name" required value={formData.name} onChange={handleChange}
                className="w-full px-4 py-3 rounded-lg border border-gray-200 focus:border-rzp-blue focus:ring-2 focus:ring-rzp-blue/20 outline-none transition-all bg-gray-50 focus:bg-white"
                placeholder="John Doe"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">Phone Number</label>
              <input 
                type="tel" name="phone" required value={formData.phone} onChange={handleChange}
                className="w-full px-4 py-3 rounded-lg border border-gray-200 focus:border-rzp-blue focus:ring-2 focus:ring-rzp-blue/20 outline-none transition-all bg-gray-50 focus:bg-white"
                placeholder="9876543210"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">Email Address</label>
              <input 
                type="email" name="email" required value={formData.email} onChange={handleChange}
                className="w-full px-4 py-3 rounded-lg border border-gray-200 focus:border-rzp-blue focus:ring-2 focus:ring-rzp-blue/20 outline-none transition-all bg-gray-50 focus:bg-white"
                placeholder="john@example.com"
              />
            </div>

            <button 
              type="submit" 
              disabled={loading}
              className={`w-full mt-6 bg-rzp-blue hover:bg-blue-600 text-white font-medium py-3.5 px-4 rounded-lg transition-all shadow-lg shadow-blue-500/30 flex items-center justify-center space-x-2 ${loading ? "opacity-75 cursor-not-allowed" : ""}`}
            >
              {loading && !simulating && (
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              )}
              <span>{loading ? "Processing..." : "Setup Mandate securely"}</span>
            </button>
          </form>
          
          <p className="text-center text-xs text-gray-400 mt-6 font-mono flex items-center justify-center space-x-2">
            <span>Powered by</span>
            <span className="font-bold text-gray-600 tracking-wider">RAZORPAY</span>
          </p>
        </div>
      </div>
    </div>
  );
}
