import React from "react";
import { Search } from "lucide-react";

export const SearchBar = ({ value, onChange }) => {
  return (
    <div className="search-container">
      <Search className="search-icon" size={18} />
      <input
        type="text"
        className="search-input"
        placeholder="Search by Phone Number or Order ID..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
};
